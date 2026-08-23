# Bounded integer counter (reference companion)

This companion is not a customer, industry, geography, or certifier.

It is a domain-generic example of a bounded integer counter. It is not one of
the 26 core intake templates and must not constrain architecture, industry,
geography, or certification.

## Requirements

- REQ-1. The system maintains a single integer counter whose value is at least
  zero and at most a configured inclusive upper bound.
- REQ-2. Incrementing the counter when it already equals the upper bound is
  refused and leaves the stored value unchanged.
- REQ-3. Decrementing the counter when it equals zero is refused and leaves the
  stored value unchanged.

## Acceptance criteria

- AC-1. Given bound 3 and value 0, increment three times yields 3; a fourth
  increment is refused and the value stays 3.
- AC-2. Given value 0, decrement is refused and the value stays 0.
- AC-3. The configured bound is a positive integer; a non-positive bound is
  refused before any count is stored.
