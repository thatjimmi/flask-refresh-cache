import time
import atexit
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from flask import request, jsonify

class CacheManager:
    def __init__(self, app, cache, executor=None):
        self.app = app
        self.cache = cache
        self.executor = executor or ThreadPoolExecutor()
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        atexit.register(lambda: self.executor.shutdown(wait=False))
        atexit.register(lambda: self.scheduler.shutdown())
        

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
                self.executor.submit(self.update_cache, key, compute_func, refreshing_key)
                
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
                    self.executor.submit(self.update_cache, key, compute_func, refreshing_key)
                return value['data']
        else:
            print(f'Cache miss for key: {key}')
            new_value = compute_func()
            self.update_cache(key, compute_func)
            return new_value

    def update_cache(self, key, compute_func, refreshing_key=None):
        """
        Updates the cache and removes any refreshing flags.

        Args:
            key (str): Cache key.
            compute_func (Callable): Function to compute fresh data.
            refreshing_key (str, optional): Temporary flag key for ongoing refresh.
        """
        with self.app.app_context():
            precomputed_value = compute_func()
            self.cache.set(key, {'data': precomputed_value, 'timestamp': time.time()})
            print(f'Updated cache for key: {key} at {time.strftime("%Y-%m-%d %H:%M:%S")}')
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
                self.update_cache(key, compute_func)

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