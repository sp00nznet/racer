# =============================================================================
# Star Wars Episode I: Racer - N64 Static Recompilation
# =============================================================================
# "Now THIS is podracing!" - Anakin Skywalker
#
# Makefile for building the recompiled PC port using N64Recomp
# =============================================================================

# Configuration
ROM          := baserom.z64
SYMBOLS      := symbols.toml
RECOMP_TOML  := recomp.toml
OUTPUT_DIR   := RecompiledFuncs
BUILD_DIR    := build
N64RECOMP    ?= N64Recomp

# Python (try py first for Windows, then python3, then python)
PYTHON       := $(shell command -v py 2>/dev/null || command -v python3 2>/dev/null || command -v python 2>/dev/null)

# Tools
ANALYZER     := tools/rom_analyzer.py
DIFFER       := tools/func_differ.py
STRINGS      := tools/string_dumper.py
PROGRESS     := tools/progress.py

# Expected ROM checksums (US version)
EXPECTED_CRC := 72F70398
ROM_SIZE     := 33554432

# Colors
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
CYAN   := \033[0;36m
NC     := \033[0m

# =============================================================================
# Default target
# =============================================================================

.PHONY: all
all: verify analyze
	@echo ""
	@echo "$(GREEN)  ================================================$(NC)"
	@echo "$(GREEN)  =  READY FOR RECOMPILATION                     =$(NC)"
	@echo "$(GREEN)  =  Run 'make recomp' when N64Recomp is built   =$(NC)"
	@echo "$(GREEN)  ================================================$(NC)"
	@echo ""

# =============================================================================
# ROM verification
# =============================================================================

.PHONY: verify
verify: $(ROM)
	@echo ""
	@echo "$(CYAN)  Verifying ROM...$(NC)"
	@$(PYTHON) -c "                                                      \
		import struct;                                                    \
		f = open('$(ROM)', 'rb'); data = f.read(); f.close();            \
		crc1 = struct.unpack('>I', data[16:20])[0];                      \
		expected = 0x$(EXPECTED_CRC);                                     \
		size = len(data);                                                 \
		ok = crc1 == expected and size == $(ROM_SIZE);                    \
		status = 'PASS' if ok else 'FAIL';                               \
		print(f'  CRC: 0x{crc1:08X} (expected 0x{expected:08X}) [{status}]'); \
		print(f'  Size: {size:,} bytes [{\"PASS\" if size == $(ROM_SIZE) else \"FAIL\"}]'); \
		exit(0 if ok else 1)                                             \
	"
	@echo "$(GREEN)  ROM verified!$(NC)"

$(ROM):
	@echo "$(RED)  ERROR: $(ROM) not found!$(NC)"
	@echo "  Place your Star Wars Episode I: Racer (US) ROM as '$(ROM)'"
	@echo "  Expected: NEPE / CRC 0x$(EXPECTED_CRC)"
	@exit 1

# =============================================================================
# Analysis
# =============================================================================

.PHONY: analyze
analyze: $(ROM)
	@echo ""
	@echo "$(CYAN)  Running ROM analysis...$(NC)"
	@$(PYTHON) $(ANALYZER) $(ROM)

.PHONY: symbols
symbols: $(ROM)
	@echo "$(CYAN)  Regenerating symbols.toml...$(NC)"
	@$(PYTHON) $(ANALYZER) $(ROM)

# =============================================================================
# Recompilation (requires N64Recomp binary)
# =============================================================================

.PHONY: recomp
recomp: verify $(SYMBOLS) $(RECOMP_TOML)
	@echo ""
	@echo "$(CYAN)  Running N64Recomp...$(NC)"
	@echo "  Config: $(RECOMP_TOML)"
	@echo "  Symbols: $(SYMBOLS)"
	@echo ""
	@mkdir -p $(OUTPUT_DIR)
	$(N64RECOMP) $(RECOMP_TOML)
	@echo ""
	@echo "$(GREEN)  Recompilation complete!$(NC)"
	@echo "  Output in $(OUTPUT_DIR)/"

# =============================================================================
# Debug tools
# =============================================================================

.PHONY: strings
strings: $(ROM)
	@$(PYTHON) $(STRINGS) $(ROM)

.PHONY: strings-debug
strings-debug: $(ROM)
	@$(PYTHON) $(STRINGS) $(ROM) -c debug

.PHONY: strings-game
strings-game: $(ROM)
	@$(PYTHON) $(STRINGS) $(ROM) -c game

.PHONY: strings-menu
strings-menu: $(ROM)
	@$(PYTHON) $(STRINGS) $(ROM) -c menu

.PHONY: strings-files
strings-files: $(ROM)
	@$(PYTHON) $(STRINGS) $(ROM) -c files

.PHONY: progress
progress:
	@$(PYTHON) $(PROGRESS) $(SYMBOLS)

# Disassemble a function: make diff FUNC=func_80000470
.PHONY: diff
diff: $(ROM)
ifndef FUNC
	@echo "  Usage: make diff FUNC=func_80000470"
	@echo "         make diff FUNC=0x80000470"
else
	@$(PYTHON) $(DIFFER) $(FUNC) $(ROM)
endif

# =============================================================================
# Housekeeping
# =============================================================================

.PHONY: clean
clean:
	rm -rf $(OUTPUT_DIR) $(BUILD_DIR)
	@echo "$(GREEN)  Cleaned build output.$(NC)"

.PHONY: cleanall
cleanall: clean
	rm -f symbols.toml
	@echo "$(GREEN)  Cleaned everything.$(NC)"

.PHONY: setup
setup:
	@echo "$(CYAN)  Checking dependencies...$(NC)"
	@$(PYTHON) --version
	@echo ""
	@echo "  To build N64Recomp:"
	@echo "    cd /path/to/N64Recomp"
	@echo "    cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release"
	@echo "    cmake --build build --config Release"
	@echo ""
	@echo "  Place your ROM as '$(ROM)' and run 'make'"

.PHONY: help
help:
	@echo ""
	@echo "  $(CYAN)Star Wars Episode I: Racer - N64 Static Recomp$(NC)"
	@echo "  ================================================"
	@echo ""
	@echo "  $(GREEN)make$(NC)              - Verify ROM and run analysis"
	@echo "  $(GREEN)make verify$(NC)       - Verify ROM checksum"
	@echo "  $(GREEN)make analyze$(NC)      - Analyze ROM and generate symbols"
	@echo "  $(GREEN)make recomp$(NC)       - Run N64Recomp (requires built tool)"
	@echo "  $(GREEN)make symbols$(NC)      - Regenerate symbols.toml"
	@echo ""
	@echo "  $(YELLOW)Debug Tools:$(NC)"
	@echo "  $(GREEN)make progress$(NC)     - Show recomp progress"
	@echo "  $(GREEN)make diff FUNC=X$(NC)  - Disassemble a function"
	@echo "  $(GREEN)make strings$(NC)      - Dump all strings"
	@echo "  $(GREEN)make strings-debug$(NC) - Show debug strings"
	@echo "  $(GREEN)make strings-game$(NC)  - Show game strings"
	@echo "  $(GREEN)make strings-menu$(NC)  - Show menu strings"
	@echo "  $(GREEN)make strings-files$(NC) - Show file path strings"
	@echo ""
	@echo "  $(YELLOW)Housekeeping:$(NC)"
	@echo "  $(GREEN)make clean$(NC)        - Remove build output"
	@echo "  $(GREEN)make cleanall$(NC)     - Remove everything"
	@echo "  $(GREEN)make setup$(NC)        - Check dependencies"
	@echo "  $(GREEN)make help$(NC)         - This message"
	@echo ""
