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
    time.sleep(10)
    return f"Delta Positions at {time.strftime('%Y-%m-%d %H:%M:%S')}"

def compute_product_betas():
    time.sleep(4)
    return f"Product betas at {time.strftime('%Y-%m-%d %H:%M:%S')}"

def compute_trade_summary():
    time.sleep(5) 
    return f"Trade Summary at {time.strftime('%Y-%m-%d %H:%M:%S')}"

# Flask routes
# @app.route('/delta_positions')
# @cache_manager.cacher(timeout=20, refresh_margin=10)
# def delta_positions():
#     return compute_delta_positions()

# @app.route('/trade_summary')
# @cache_manager.cacher(timeout=10, refresh_margin=0)
# def trade_summary():
#     return compute_trade_summary()

@app.route('/product_betas')
@cache_manager.cacher(timeout=0, refresh_margin=0)
def product_betas():
    return compute_product_betas()

# Schedule periodic refresh
# cache_manager.schedule_periodic_refresh('/trade_summary', interval=10, compute_func=compute_trade_summary)  