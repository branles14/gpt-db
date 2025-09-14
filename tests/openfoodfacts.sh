#!/bin/bash

# Ensure UPC is given
if [[ -z "$1" ]]; then
    echo "ERROR: Mussing UPC"
    exit 1
else
    upc="$1"
fi

# Request product data
if ! data=$(curl -s "https://world.openfoodfacts.org/api/v2/product/${upc}.json"); then
    echo "ERROR: Failed to get data from openfoodfacts.org"
    exit 1
fi

# Check if product exists
status=$(jq '.status' <<< "$data")
if [[ ! "$status" -eq 1 ]]; then
    echo "ERROR: Product not found"
    exit 1
fi

# Ensure product name is defined
product_name=$(jq -r '.product.product_name' <<< "$data")
if [[ -z "$product_name" ]]; then
    echo "ERROR: Product name not found"
    exit 1
fi

# Output product name
echo "$product_name"
