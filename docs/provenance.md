# Scientific provenance and competing tools

The implementation is original code under MIT. It implements standard uniformization and does not claim a new sampling algorithm or first Python bridge generator.

- Hobolth and Stone (2009), “Simulation from endpoint-conditioned, continuous-time Markov chains on a finite state space,” supplies the classical uniformization treatment and a published HKY example: https://pmc.ncbi.nlm.nih.gov/articles/PMC2818752/ . Section 3.1 uses kappa=2 and stationary frequencies (1/5,3/10,3/10,1/5) in A,G,C,T order, normalized to mean stationary exit rate 1. Our JSON re-expresses those mathematical parameters. Our demonstration horizon 1/5 is an explicit choice. We do not redistribute article text, figures or its supplementary R code; availability of the article is not an open-source license.
- DendroPy's BSD-3-Clause `Hky85` source independently corroborates the matrix family, normalization and analytical probabilities: https://github.com/jeetsukumaran/DendroPy/blob/f11c65473b0d105d514e46466cb77442e886aaf1/src/dendropy/model/discrete.py#L259-L369 . It orders states A,C,G,T, so axes must be permuted. Its JOSS paper is CC-BY-4.0: https://joss.theoj.org/papers/10.21105/joss.06943 . No DendroPy code is copied or needed at runtime.
- mbridges already generates full trajectories and has scientific workflows: https://doi.org/10.1103/PhysRevResearch.7.013010 . The MIT reference implementation is compared at commit b567f07c4f703e07e14f27cabee9609f2db723e1: https://github.com/gletreut/markov-bridges . Its eigen-based backward probabilities and configurable threshold have a different numerical contract. Its source is not bundled in this package.
- ECctmc supplies established full-path modified-rejection and uniformization algorithms, including endpoint-conditioned event-count accumulation: https://github.com/fintzij/ECctmc . It is GPL-3. We do not copy its code or claim it makes an unconditional-cutoff mistake.
- ctmcd supplies transition-count/occupation workflows and a GPL-3 uniformization core: https://cran.r-project.org/package=ctmcd . Its continued availability is not evidence of an abandoned field. Its code is not included here.

For the published HKY model in A,G,C,T order,

`Q=(1/49)*[[-55,30,15,10],[20,-45,15,10],[10,15,-45,20],[10,15,30,-55]]`.

An independently derived endpoint formula is
`P_AG(t)=3/10+(3/10)*exp(-50*t/49)-(3/5)*exp(-75*t/49)`.
With uniformization rate 55/49,
`(R**n)[A,G]=3/10+(3/10)*(1/11)**n-(3/5)*(-4/11)**n`.
These are mathematical model facts expressed in original code/prose, not copied empirical data. Synthetic rare-switch and birth-chain examples are likewise original mathematical fixtures.

Poor relative accuracy of a very rare entry from a floating matrix exponential is not automatically a correctness bug or a violation of normwise accuracy expectations. Comparison reports distinguish full baseline executions, source inspection, numerical diagnostics and unavailable experiments.
