# Knowledge Layer research notes

## Railway/browser note
The browser navigation to the LibreTexts result did not retain the page and displayed about:blank on the follow-up view. The same official/public source was successfully extracted through the web page extraction step.

## Engineering source
1. Engineering LibreTexts, “18.5: Volumetric Factors (Bo and Bg)”
   URL: https://eng.libretexts.org/Bookshelves/Chemical_Engineering/Phase_Relations_in_Reservoir_Engineering_(Adewumi)/18%3A_Properties_of_Natural_Gas_and_Condensates_I/18.05%3A_Volumetric_Factors_(Bo_and_Bg)
   Use: reference for the distinction and reservoir-condition meaning of Bo and Bg.

2. Railway storage source was reviewed separately in the previous task; it is not an engineering source for this increment.

The knowledge dataset will use established petroleum-engineering terminology, conservative definitions, explicit units/conventions, and a verification status. It will not introduce numerical calculation formulas as independent solvers.

## Additional engineering sources

3. SLB Energy Glossary, “oil formation volume factor”
   URL: https://glossary.slb.com/terms/o/oil_formation_volume_factor
   Use: Bo is the oil and dissolved-gas volume at reservoir conditions divided by oil volume at standard conditions; the source explains why Bo is commonly greater than 1.0 and why volume factors convert surface measurements to reservoir conditions.

4. SLB Energy Glossary, “productivity index (PI)”
   URL: https://glossary.slb.com/terms/p/productivity_index_pi.aspx
   Use: PI expresses the reservoir’s ability to deliver fluids to the wellbore and is commonly stated as volume per psi of drawdown at the sandface, e.g. bbl/d/psi.

5. SLB Energy Glossary, “GOR”
   URL: https://glossary.slb.com/terms/g/gor
   Use: GOR is the abbreviation for gas/oil ratio, the ratio of produced gas to produced oil.

6. whitson+, “IPR/VLP — Nodal Analysis”
   URL: https://manual.whitson.com/modules/well-performance/nodal-analysis/
   Use: reference for the distinction between reservoir inflow (IPR), vertical lift/outflow (VLP), productivity-index context, and nodal operating-point interpretation.

The SLB glossary pages are publicly readable through extraction but display an account/premium notice after the glossary entry; the definitions above are taken from the visible entry text only. No hidden or premium material is used.

The direct browser view of the SLB GOR page confirmed that GOR is the abbreviation for gas/oil ratio and means the ratio of produced gas to produced oil. The page also lists produced fluid as a related term. URL: https://glossary.slb.com/terms/g/gor

## PVT coverage verification

7. SLB Energy Glossary, “PVT”
   URL: https://glossary.slb.com/terms/p/pvt
   Use: PVT is an abbreviation for pressure, volume, and temperature; SLB states that the term is used in fluid-properties evaluations.

8. Core Laboratories, “Phase Behavior and PVT”
   URL: https://www.corelab.com/services/phase-behavior-and-pvt/
   Use: PVT measurements support understanding phase behavior and fluid properties of gases and liquids at reservoir conditions, and are used in reservoir management, production optimization, and reservoir simulation.

This supports adding a concise PVT concept record. No numerical PVT correlation or solver is introduced.

9. SLB Energy Glossary, “viscosity”
   URL: https://glossary.slb.com/terms/v/viscosity
   Use: viscosity indicates resistance to flow; SLB notes that cP is commonly used, one cP equals one mPa·s, and meaningful viscosity requires a stated or understood shear rate and measurement temperature.
