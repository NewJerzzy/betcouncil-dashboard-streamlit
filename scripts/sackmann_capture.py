import json, requests, os
with open('/tmp/out.log') as f:
    content = f.read()
resp = requests.patch(
    'https://api.github.com/gists/7e52e1c2c2054847c7c4663a157386c5',
    headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'], 'Accept': 'application/vnd.github+json'},
    json={'files': {'betcouncil_bettingpros_debug.json': {'content': json.dumps({'note': 'TEMP sackmann real run output', 'log': content[-4000:]})}}}
)
print('debug push:', resp.status_code)
