<%*
// Decision.md — Templater template for Path B decision records (MADR format).
// One file per decision at <vault>/Decisions/D-NNN.md.

const id      = await tp.system.prompt("Decision ID (e.g. 099, 100)");
const project = await tp.system.prompt("Project slug");
const topic   = await tp.system.suggester(
  ["architecture", "process", "tooling", "data-model", "infra", "security", "ux"],
  ["architecture", "process", "tooling", "data-model", "infra", "security", "ux"],
  false, "Topic");
const title   = await tp.system.prompt("Title (one short line)");
const today   = tp.date.now("YYYY-MM-DD");
-%>
---
schema_version: 1
id: D-<% id %>
date: <% today %>
project: <% project %>
topic: <% topic %>
title: "<% title %>"
status: proposed
linked:
  patterns: []
  issues: []
  prs: []
  related_decisions: []
created_at: <% today %>
---

# D-<% id %> — <% title %>

## Context
*(what's the problem; what constraints exist)*

## Decision
*(what we're choosing to do)*

## Alternatives considered
- **Option A**: 
  - Rejected because: 
- **Option B**: 
  - Rejected because: 

## Reasoning
*(why this is the right call given context + alternatives)*

## Outcome
*(filled in later when shipped — what actually happened)*

## Linked
- Patterns: 
- PRs: 
- Issues: 
- Related decisions: 
