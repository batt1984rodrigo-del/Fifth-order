# External Validation Protocol

This directory contains the external validation layer for the Quinta Ordem Gate.

The purpose of this layer is to validate the gate with closed real cases while preserving chain of custody and keeping the MVP core frozen during the first validation cycle.

## Core rule

The validation layer must not modify the Quinta Ordem Gate core.

Any change to weights, rules, verifiers, thresholds, schemas or core behavior must happen only after the first validation cycle is formally closed and documented.

## What this layer does

- computes real SHA-256 hashes during ingestion;
- records evidence inventories;
- stores expected human review separately before execution;
- records execution metadata;
- runs cases through the existing gate contract;
- compares gate output against human review;
- documents divergences, false approvals, false blocks and missed findings;
- verifies reproducibility of equivalent bundles.

## What this layer does not do

- it does not alter original evidence;
- it does not store real sensitive documents in the public repository;
- it does not train or tune the gate during the validation lot;
- it does not use the gate as an autonomous decision maker;
- it does not treat agreement with human review as proof of factual or legal truth.

## Validation cycle

The first cycle requires three controlled cases:

1. one closed legal case;
2. one closed administrative or tax process;
3. one controlled documentary pipeline with intentional variation.

## Reproducibility dimensions

Reproducibility must be evaluated separately as:

1. decision reproducibility;
2. report-content reproducibility;
3. byte-for-byte bundle identity.

If timestamps, absolute paths, environment-specific metadata or volatile values are included in the context, they must be frozen, normalized or explicitly documented.

## Safety

Only anonymized, synthetic or non-sensitive derived fixtures may be committed to the public repository.

Real evidence must remain outside the public repository and must be referenced only through controlled identifiers, hashes, manifests and anonymized metadata.
