#!/bin/bash

# Generates a PDF containing documentation for the Puppet modules present in a Puppet environment (environment-XXXX).

# Dependencies:
# Python > 3.6: confirmed works without issue using Python 3.9 Virtual Environment
# Puppet Strings: https://puppet.com/docs/puppet/5.5/puppet_strings.html
# Pandoc: apt install texlive-latex-extra; apt install pandoc
# pdftk: Ubuntu/Debian - apt install pdftk / Windows: https://www.pdflabs.com/t/cli/

# At the moment, designed to sit in an environment-XXXX repo itself, as it makes use of paths relative to $PWD like ./XXXX
# This is because Puppet Strings includes the full path in the docs (annoyingly) so it works "neater" being run like this.
# Can be made to a proper binary, with Makefile for install, etc

if [[ ! -d ./modules ]]
then
	echo "Call this script from a Puppet environment with the Puppet modules located inside '<environment-XXXX>/modules' directory."
	exit
fi

CURRENT_TAG=$(git tag --points-at HEAD)
CURRENT_COMMIT=$(git rev-parse --verify HEAD)

# If HEAD has a tag, use this in PDF naming (preferred), else use current commit
if [ -z "$CURRENT_TAG" ]
then
  PDF_NAME_SUFFIX=$CURRENT_COMMIT
else
  PDF_NAME_SUFFIX=$CURRENT_TAG
fi

rm -rf ./pdf 2>/dev/null
rm ./module_docs_* 2> /dev/null

if [[ ! -d ./pdf ]]
then
	mkdir ./pdf
fi

if [[ ! -d ./markdown ]]
then
	mkdir ./markdown
fi

echo "Generating Puppet module documentation ..."
echo ""

manifests=[]

# Following line for testing
#for module in $(ls ./modules | head -n 3)
for module in $(ls ./modules)
do
	echo "$module ..."
	# Generate module doc HTML from init.pp documentation using Puppet Strings
	puppet strings generate --format markdown ./modules/$module/manifests/init.pp --out ./markdown/$module.md >> ./module_docs_$PDF_NAME_SUFFIX.log 2>&1
# Convert module doc HTML to PDF using Python module weasyprint
#	python -W ignore -m weasyprint -q ./doc/puppet_classes/$module.html ./pdf/$module.pdf >> ./module_docs_$PDF_NAME_SUFFIX.log 2>&1
  # Convert module doc markdown to PDF using pandoc
  pandoc --from markdown ./markdown/$module.md -o ./pdf/$module.pdf >> ./module_docs_$PDF_NAME_SUFFIX.log 2>&1
done

# Merge all generated module doc PDFs using pdftk
pdftk ./pdf/* cat output ./module_docs_$PDF_NAME_SUFFIX.pdf

echo ""
echo "Documentation successfully generated: ./module_docs_$PDF_NAME_SUFFIX.pdf"

rm -rf ./pdf
rm -rf ./markdown
