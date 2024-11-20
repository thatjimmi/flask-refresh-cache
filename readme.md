# Python Caching Mechanism with Stale-While-Revalidate

This Python project provides a flexible caching mechanism that implements the stale-while-revalidate strategy for Flask-based web applications. It optimizes response times for slow, infrequently updated resources by serving cached data while asynchronously refreshing it in the background when the cache is about to expire. The system also supports background cache refreshes, automatic cache key generation, and periodic cache updates, ensuring that data stays up-to-date without blocking user requests. This approach is ideal for long-running computations or rarely updated data, enabling efficient caching for dynamic resources.

## Features

- **Stale-While-Revalidate**: Returns cached (stale) data while refreshing the cache in the background.
- **Automatic Cache Key Generation**: Cache keys are generated based on the route and query parameters.
- **Background Cache Refresh**: Cache can be periodically refreshed in the background using APScheduler.
- **Thread Pool Executor**: Supports asynchronous cache updates using a thread pool.

To install the required dependencies, use the following command:

```bash
pip install flask apscheduler
```

## Example Usage

```python
import time
from flask import Flask
from flask_caching import Cache
from cache_manager import CacheManager

app = Flask(__name__)
app.config['CACHE_TYPE'] = 'SimpleCache'
cache = Cache()
cache.init_app(app)
cache_manager = CacheManager(app, cache)

def compute_delta_positions():
    time.sleep(10) # SLOW COMPUTATION
    return f"Delta Positions at {time.strftime('%Y-%m-%d %H:%M:%S')}"

@app.route('/delta_positions')
@cache_manager.cacher(timeout=20, refresh_margin=10)
def delta_positions():
    return compute_delta_positions()

# Schedule periodic refresh
cache_manager.schedule_periodic_refresh('/delta_positions', interval=10 compute_func=compute_delta_positions)
```

In the example above, the route /some-resource is cached for 1 hour (timeout=3600 seconds) and will begin refreshing 5 minutes before expiration (refresh_margin=300 seconds).
