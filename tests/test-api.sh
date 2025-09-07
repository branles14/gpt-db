#!/bin/bash

# Error Checks
if [[ -z "${API_KEY}" ]]; then
    echo "ERROR: Undefined variable: API_KEY"
    exit 1
elif [[ -z "${API_URL}" ]]; then
    echo "ERROR: Undefined variable: API_URL"
    exit 1
fi

curl -s -H "x-api-key: ${API_KEY}" "${API_URL}/" | jq
