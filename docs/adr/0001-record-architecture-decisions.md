# 1. Record Architecture Decisions

## Status
Accepted

## Context
As the project evolves, decisions like "why Python", "why AWS Lambda", "why per-category SMS" need to stay traceable instead of getting lost.

## Decision
Every significant architecture decision is recorded under `docs/adr/` as a numbered markdown file using the format: Status / Context / Decision / Consequences.

## Consequences
A new agent, or the project owner months later, can answer "why was this built this way" without doing code archaeology.
