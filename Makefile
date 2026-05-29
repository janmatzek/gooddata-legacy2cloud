# (C) 2026 GoodData Corporation
.PHONY: dev
dev:
	uv sync --all-groups
	uv run pre-commit install

	@echo "\n\nRun 'source .venv/bin/activate' to activate the virtual environment"

.PHONY: install-skill
install-skill:
	mkdir -p ~/.claude/skills/gooddata-platform2cloud-cli
	ln -sf "$(CURDIR)/.claude/skills/gooddata-platform2cloud-cli/SKILL.md" \
		~/.claude/skills/gooddata-platform2cloud-cli/SKILL.md
	@echo "Skill installed. Restart Claude Code to pick up changes."

.PHONY: format
format:
	.venv/bin/ruff format .

.PHONY: format-check
format-check:
	.venv/bin/ruff format --check .

.PHONY: lint
lint:
	.venv/bin/ruff check

.PHONY: type
type:
	.venv/bin/ty check

.PHONY: test
test:
	.venv/bin/pytest


.PHONY: check
check: format lint test type

.PHONY: release-ci
release-ci:
	if [ -z "$(VERSION)" ]; then echo "Usage: 'make release-ci VERSION=X.Y.Z'"; false; else \
	uv run tbump $(VERSION) --only-patch --non-interactive && uv lock ; fi
