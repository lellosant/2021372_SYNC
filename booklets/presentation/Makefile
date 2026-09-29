MAIN       = main
BUILD_DIR  = build
OUTPUT_DIR = outputs
SLIDES     = $(wildcard slides/*.tex)

PDFLATEX_FLAGS = -output-directory=$(BUILD_DIR)

.PHONY: all clean

all: $(OUTPUT_DIR)/$(MAIN).pdf

$(OUTPUT_DIR)/$(MAIN).pdf: $(MAIN).tex $(wildcard *.sty) $(SLIDES) | $(BUILD_DIR) $(OUTPUT_DIR)
	pdflatex $(PDFLATEX_FLAGS) $(MAIN).tex
	pdflatex $(PDFLATEX_FLAGS) $(MAIN).tex
	cp $(BUILD_DIR)/$(MAIN).pdf $(OUTPUT_DIR)/$(MAIN).pdf

$(BUILD_DIR) $(OUTPUT_DIR):
	-mkdir $@

clean:
	rm -rf $(BUILD_DIR)
	rm -f $(OUTPUT_DIR)/$(MAIN).pdf
