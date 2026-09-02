#!/bin/bash
# R165 — register + verify (console token from the server log) + login two
# principals against a live `python3 -m apps.main` whose stdout is at
# /tmp/r165/server.log: ops@example.com (in ADMIN_EMAILS) and dev@example.com.
# Tokens land in /tmp/r165/{ops,dev}.tok. Passwords are throwaway test values.
B=${B:-http://127.0.0.1:8000}; cd /tmp/r165 || exit 1
for u in ops dev; do
  curl -s -X POST $B/v1/auth/register -H 'content-type: application/json' \
    -d "{\"email\":\"$u@example.com\",\"password\":\"Str0ng-Passw0rd-$u-2026\"}" > /dev/null
done
sleep 1
grep -a -o '{"event": "email_verification_token_issued"[^}]*}' server.log | tail -2 > tokens.json
python3 - <<'EOF'
import json, subprocess
B = "http://127.0.0.1:8000"
for line in open("/tmp/r165/tokens.json"):
    e = json.loads(line); email = e["email"]; u = email.split("@")[0]
    subprocess.run(["curl", "-s", "-X", "POST", f"{B}/v1/auth/verify", "-H", "content-type: application/json",
                    "-d", json.dumps({"token": e["token"]})], capture_output=True)
    r = subprocess.run(["curl", "-s", "-X", "POST", f"{B}/v1/auth/login", "-H", "content-type: application/json",
                        "-d", json.dumps({"email": email, "password": f"Str0ng-Passw0rd-{u}-2026"})],
                       capture_output=True, text=True)
    open(f"/tmp/r165/{u}.tok", "w").write(json.loads(r.stdout)["token"]); print("login ok", email)
EOF
rm -f tokens.json
