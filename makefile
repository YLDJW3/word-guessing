LOG_DIR := logs

server:
	uv run server.py --allow-names-file allowlist.txt

tunnel:
	cloudflared tunnel --url http://localhost:8000

# Detached background variants: survive terminal close, output to logs/*.log, pid to logs/*.pid.
server-bg:
	@mkdir -p $(LOG_DIR)
	@nohup uv run server.py --allow-names-file allowlist.txt > $(LOG_DIR)/server.log 2>&1 & echo $$! > $(LOG_DIR)/server.pid
	@echo "server started (pid $$(cat $(LOG_DIR)/server.pid)) → $(LOG_DIR)/server.log"

tunnel-bg:
	@mkdir -p $(LOG_DIR)
	@nohup cloudflared tunnel --url http://localhost:8000 > $(LOG_DIR)/tunnel.log 2>&1 & echo $$! > $(LOG_DIR)/tunnel.pid
	@echo "tunnel started (pid $$(cat $(LOG_DIR)/tunnel.pid)) → $(LOG_DIR)/tunnel.log"

stop:
	@for p in server tunnel; do \
		if [ -f $(LOG_DIR)/$$p.pid ]; then \
			kill $$(cat $(LOG_DIR)/$$p.pid) 2>/dev/null && echo "stopped $$p (pid $$(cat $(LOG_DIR)/$$p.pid))" || echo "$$p not running"; \
			rm -f $(LOG_DIR)/$$p.pid; \
		else \
			echo "$$p: no pid file"; \
		fi; \
	done

status:
	@for p in server tunnel; do \
		if [ -f $(LOG_DIR)/$$p.pid ] && kill -0 $$(cat $(LOG_DIR)/$$p.pid) 2>/dev/null; then \
			echo "$$p: running (pid $$(cat $(LOG_DIR)/$$p.pid))"; \
		else \
			echo "$$p: not running"; \
		fi; \
	done

logs:
	@mkdir -p $(LOG_DIR)
	@touch $(LOG_DIR)/server.log $(LOG_DIR)/tunnel.log
	@tail -n 50 -f $(LOG_DIR)/server.log $(LOG_DIR)/tunnel.log

.PHONY: server tunnel server-bg tunnel-bg stop status logs
