#!/usr/bin/env bash
# Wrapper to run Elasticsearch with correct JAVA_HOME (ARM Mac).
# Use when brew's bundled JDK has "Bad CPU type" error.
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home}"
exec /opt/homebrew/opt/elasticsearch-full/bin/elasticsearch "$@"
