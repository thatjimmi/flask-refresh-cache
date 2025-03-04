import time
import atexit
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from flask import request, jsonify, current_app

class CacheManager:
    def __init__(self, app=None, cache=None, executor=None):
        self.app = app
        self.cache = cache
        self.executor = executor or ThreadPoolExecutor()
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        atexit.register(lambda: self.executor.shutdown(wait=False))
        atexit.register(lambda: self.scheduler.shutdown())
        
        # Setup app if provided
        if app is not None:
            self.init_app(app, cache)

    def init_app(self, app, cache=None):
        """
        Initialize the CacheManager with a Flask app.
        This allows for initialization after instance creation.
        
        Args:
            app: Flask app instance
            cache: Cache instance (if not provided earlier)
        """
        self.app = app
        if cache is not None:
            self.cache = cache

    def _generate_key(self):
        """
        Automatically generate a cache key based on the current route and request arguments.
        """
        route = request.path  
        args = request.args.copy()
        
        # Remove force_refresh parameter from the cache key generation
        if 'force_refresh' in args:
            args.pop('force_refresh')
            
        query_string = '&'.join([f'{k}={v}' for k, v in args.items()])
        if query_string:
            return f'{route}?{query_string}'
        return route

    def stale_while_revalidate(self, timeout, refresh_margin, compute_func):
        """
        Implements stale-while-revalidate logic for caching.

        Args:
            timeout (int): Cache expiration time (in seconds).
            refresh_margin (int): Time to refresh the cache before it expires (in seconds).
            compute_func (Callable): Function to compute fresh data.

        Returns:
            Any: Cached or computed data.
        """
        key = self._generate_key()
        
        # Check if force_refresh is in the request parameters
        force_refresh = request.args.get('force_refresh', '').lower() in ('true', '1', 'yes')
        
        # Handle the force refresh scenario
        if force_refresh:
            print(f'Force refresh requested for key: {key}')
            refreshing_key = f"{key}_refreshing"
            
            # Only trigger a refresh if not already refreshing
            if not self.cache.get(refreshing_key):
                self.cache.set(refreshing_key, True, timeout=refresh_margin)
                self.executor.submit(self._safe_update_cache, key, compute_func, refreshing_key)
                
            # Just return a success message for force refresh requests
            return {'status': 'OK', 'message': 'Cache refresh triggered in background'}
            
        # Normal caching flow
        value = self.cache.get(key)
        if value is not None:
            last_update = value.get('timestamp', 0)
            if time.time() - last_update < timeout - refresh_margin:
                print(f'Cache hit for key: {key}')
                return value['data']
            else:
                print(f'Cache stale for key: {key}')
                refreshing_key = f"{key}_refreshing"
                if not self.cache.get(refreshing_key):
                    self.cache.set(refreshing_key, True, timeout=refresh_margin)
                    self.executor.submit(self._safe_update_cache, key, compute_func, refreshing_key)
                return value['data']
        else:
            print(f'Cache miss for key: {key}')
            new_value = compute_func()
            self._safe_update_cache(key, lambda: new_value)
            return new_value

    def _safe_update_cache(self, key, compute_func, refreshing_key=None):
        """
        Safely updates the cache with app context handling.
        This is an internal method that wraps update_cache with proper context handling.
        """
        if self.app:
            # If we have an app, use its context
            with self.app.app_context():
                self.update_cache(key, compute_func, refreshing_key)
        else:
            # If no app is provided, try to use current_app if we're within a Flask request
            try:
                # Check if we're already in an application context
                _ = current_app.name
                self.update_cache(key, compute_func, refreshing_key)
            except RuntimeError:
                # Not in a Flask context, so just update directly
                self.update_cache(key, compute_func, refreshing_key)

    def update_cache(self, key, compute_func, refreshing_key=None):
        """
        Updates the cache and removes any refreshing flags.
        This method assumes it's already in the right context.

        Args:
            key (str): Cache key.
            compute_func (Callable): Function to compute fresh data.
            refreshing_key (str, optional): Temporary flag key for ongoing refresh.
        """
        try:
            precomputed_value = compute_func()
            self.cache.set(key, {'data': precomputed_value, 'timestamp': time.time()})
            print(f'Updated cache for key: {key} at {time.strftime("%Y-%m-%d %H:%M:%S")}')
            if refreshing_key:
                self.cache.delete(refreshing_key)
        except Exception as e:
            print(f"Error updating cache for key {key}: {e}")
            if refreshing_key:
                self.cache.delete(refreshing_key)

    def schedule_periodic_refresh(self, key, interval, compute_func):
        """
        Schedules periodic cache refresh.
        """
        existing_jobs = self.scheduler.get_jobs()
        job_exists = any(job.id == key for job in existing_jobs)
        
        print("Existing jobs: ", existing_jobs)

        if not job_exists:
            def periodic_refresh_task():
                print(f'Running periodic refresh for key: {key}')
                self._safe_update_cache(key, compute_func)

            self.scheduler.add_job(periodic_refresh_task, 'interval', seconds=interval, id=key)
    
    def cacher(self, timeout, refresh_margin, compute_func=None):
        """
        Decorator for caching Flask routes or functions with stale-while-revalidate.

        Args:
            timeout (int): Cache expiration time (in seconds).
            refresh_margin (int): Time to refresh the cache before it expires (in seconds).
            compute_func (Callable, optional): Function to compute fresh data. Defaults to None.

        Returns:
            Callable: Decorated function.
        """
        def decorator(func):
            @wraps(func)
            def wrapped(*args, **kwargs):            
                nonlocal compute_func
                compute_func = compute_func or (lambda: func(*args, **kwargs))
                result = self.stale_while_revalidate(timeout, refresh_margin, compute_func)
                
                # If it's a force refresh request, wrap the result in a proper response
                if request.args.get('force_refresh', '').lower() in ('true', '1', 'yes'):
                    if isinstance(result, dict) and 'status' in result and result['status'] == 'OK':
                        return jsonify(result)
                            
                return result
            return wrapped
        return decorator