
server:
	uv run server.py --allow-names-file allowlist.txt

tunnel:
	cloudflared tunnel --url http://localhost:8000