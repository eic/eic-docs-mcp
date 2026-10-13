---
title: "Rucio Usage"
teaching: 15
exercises: 15
---

::::::::::::::::::::::::::::::::::::::::::::: questions

- How can I use Rucio?

:::::::::::::::::::::::::::::::::::::::::::::

## Getting Started

We can access and run the Rucio client from within eic-shell:

```bash
./eic-shell
rucio whoami
```

## Datasets and DIDs

Files can be grouped together into datasets which can themselves be grouped
into containers. All three refer to "data", so Rucio uses the term DID.

::::::::::::::::::::::::::::::::::::::::::::: callout

### Warning - Not a filepath!

The name of a DID looks like a filepath but it is a flat object.

:::::::::::::::::::::::::::::::::::::::::::::
