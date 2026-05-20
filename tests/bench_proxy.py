import urllib.request, json, time

PROXY = 'https://proxy-blue-kappa.vercel.app'
models = ['llama-3.3-70b', 'llama-3.1-8b', 'gemini-2.0-flash']

print(f'{"Model":25s} {"Time":>6s}  Response')
print('-' * 60)

for model in models:
    url = f'{PROXY}/v1/chat/completions'
    payload = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': 'say hi in 3 words'}],
        'stream': False,
        'temperature': 0.15,
    }).encode()
    req = urllib.request.Request(url, data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST')
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            elapsed = time.time() - start
            content = data['choices'][0]['message']['content']
            print(f'{model:25s} {elapsed:5.2f}s  "{content}"')
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        body = e.read().decode()
        print(f'{model:25s} {elapsed:5.2f}s  HTTP {e.code}: {body[:100]}')
    except Exception as e:
        elapsed = time.time() - start
        print(f'{model:25s} {elapsed:5.2f}s  ERROR: {e}')
