# Makefile — commands for using microsd-utils
#
# Only tool targets live here. Development commands (tests, ruff) are run with
# `uv` directly; see CLAUDE.md.

.PHONY: help validate stress backup flash copy card cards

.DEFAULT_GOAL := help

# The venv's script, not `uv run`: microsd re-runs itself under sudo, and sudo
# with `uv run` would leave root-owned files in .venv.
MICROSD := .venv/bin/microsd
# Long card runs: idle sleep drops the USB reader mid-pass.
AWAKE := caffeinate -i

help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} \
		/^[a-zA-Z_-]+:.*## / {printf "  %-10s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

$(MICROSD):
	uv sync

validate: $(MICROSD) ## Read-only health check of the card in the reader
	$(AWAKE) $(MICROSD) check

stress: $(MICROSD) ## Write+verify every block, WIPES the card (DRY_RUN=1 to preview)
	$(AWAKE) $(MICROSD) check --destructive $(if $(DRY_RUN),--dry-run)

backup: $(MICROSD) ## Save the card as images/NAME.img.gz (NAME=...)
	@test -n "$(NAME)" || { echo "usage: make backup NAME=<image name>"; exit 2; }
	$(AWAKE) $(MICROSD) backup "$(NAME)" $(if $(DRY_RUN),--dry-run)

flash: $(MICROSD) ## Write an image to the card, ERASES it (IMAGE=name or path)
	@test -n "$(IMAGE)" || { echo "usage: make flash IMAGE=<image name or path>"; exit 2; }
	$(AWAKE) $(MICROSD) flash "$(IMAGE)" $(if $(DRY_RUN),--dry-run)

copy: $(MICROSD) ## Copy a master card to a new card (NAME=... for its image)
	@test -n "$(NAME)" || { echo "usage: make copy NAME=<image name>"; exit 2; }
	$(AWAKE) $(MICROSD) copy "$(NAME)" $(if $(DRY_RUN),--dry-run)

card: $(MICROSD) ## Show the card's ID and history; tag it if it has none
	$(MICROSD) card $(if $(DRY_RUN),--dry-run)

cards: $(MICROSD) ## List every card in the registry
	$(MICROSD) cards
