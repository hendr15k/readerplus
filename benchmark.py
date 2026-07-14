import time
import random
from collections import OrderedDict

def benchmark_standard(n):
    cache = {}
    start = time.time()
    for i in range(n):
        cache[i] = {'t': time.time(), 'v': i}
        if len(cache) > 200:
            oldest = min(cache.items(), key=lambda x: x[1]['t'])[0]
            cache.pop(oldest, None)
    return time.time() - start

def benchmark_optimized(n):
    cache = OrderedDict()
    start = time.time()
    for i in range(n):
        cache[i] = {'t': time.time(), 'v': i}
        if len(cache) > 200:
            cache.popitem(last=False)
    return time.time() - start

print(f"Standard (10000 items): {benchmark_standard(10000):.4f}s")
print(f"Optimized (10000 items): {benchmark_optimized(10000):.4f}s")
