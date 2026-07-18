Data Specifications For Crop Revenue Insurance

**1. Geographic and unit of analysis**

1.  **Unit of analysis**
    -   County–year–crop (corn only).
    -   One observation per county per marketing year.
2.  **Geographic coverage**
    -   U.S. states: Illinois, Indiana, Iowa, Michigan, Minnesota, Ohio, Nebraska, Wisconsin.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
    -   Counties: all counties in those states with reported corn yields in USDA NASS, aiming to match 602 counties used in the paper.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
3.  **Identification variables**
    -   state_fips, county_fips (or NASS county code).
    -   state_name, county_name.
    -   year (harvest year; align with NASS convention).

**2. Yield data (USDA NASS)**

**2.1 Source and extraction**

1.  **Source**
    -   USDA National Agricultural Statistics Service (NASS) county-level yields for corn grain.[[nass.usda](https://www.nass.usda.gov/Charts_and_Maps/Field_Crops/cornyld.php)][paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
    -   Use official NASS county yield dataset(s) (Quick Stats API or downloadable county-yield files).
2.  **Variables to extract**
    -   Commodity: “CORN”.
    -   Attribute: “YIELD”.
    -   Unit: “BUSHELS / ACRE” (or equivalent).
    -   Geographic level: “COUNTY”.
    -   Years:
        -   Dataset 1 (replication): 1975–2009 inclusive.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
        -   Dataset 2 (extended): extend to latest available year (e.g., through 2025 or 2026).
    -   States: IL, IN, IA, MI, MN, OH, NE, WI.
3.  **Data cleaning**
    -   Remove records with missing or suppressed yields; document handling of “D” (withheld) and “NA”.
    -   Standardize county names and FIPS across time (handle county splits/mergers explicitly).

**2.2 Yield detrending**

The paper detrends county yields with a linear time trend and assumes homoscedastic errors.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]

1.  **Model specification (per county)**
    -   For each county $$c$$, estimate:
        -   $$y_{c , t} = \alpha_{c} + \beta_{c} t + \varepsilon_{c , t}$$, where:
            -   $$y_{c , t}$$is observed yield in bushels/acre.
            -   $$t$$is a time index (e.g., $$t = \text{year} - 1 9 7 5$$).[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
    -   Use OLS; assume independent, homoscedastic residuals around the trend.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
2.  **Detrended yields**
    -   Compute predicted trend yield: $$\widehat{y}_{c , t} = \widehat{\alpha}_{c} + \widehat{\beta}_{c} t$$.
    -   Define detrended (deviation) yield:
        -   Option A (level residuals): $$\widetilde{y}_{c , t} = y_{c , t} - \widehat{y}_{c , t}$$.
        -   Option B (relative residuals): $$\widetilde{y}_{c , t} = y_{c , t} / \widehat{y}_{c , t}$$.
    -   The paper references Sherrick et al. (2004) and describes a “linear trend form at the county levels with homoscedasticity around the trend,” but doesn’t explicitly state whether they use levels or ratios; document whichever definition you adopt, and consider storing both.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
3.  **Trend-adjusted yield series**
    -   To reproduce a “stationary” yield series for simulation:
        -   Use the residuals $$\widetilde{y}_{c , t}$$as the stochastic part.
        -   For historical-rate calculations, you can work directly with observed yields; for simulation, you may re-center around the final-year trend if you want to match their approach.
4.  **Extended period**
    -   Fit the trend on the full available period (e.g., 1975–last year) for Dataset 2.
    -   For consistency with the original period, you may also fit trend only on 1975–2009 and treat later years as out-of-sample for validation.

**3. Price data: base and harvest price construction**

**3.1 Conceptual definitions**

The paper defines the price as the percentage change between “base” and “harvest” prices.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]

1.  **Base price**
    -   Average settlement (or closing) price of December corn futures (CBOT) over February of the insurance year.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
2.  **Harvest price**
    -   Average settlement (or closing) price of December corn futures over October of the same year.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
3.  **Price variable for copula**
    -   Define:
        -   $${\text{price} \text{\_} \text{ratio}}_{t} = \text{HarvestPrice}_{t} / \text{BasePrice}_{t}$$.
        -   Or percentage change: $${\text{price} \text{\_} \text{pctchg}}_{t} = \left( \text{HarvestPrice}_{t} - \text{BasePrice}_{t} \right) / \text{BasePrice}_{t}$$.
    -   The paper states that “The price for corn is a percentage change between harvest price and base price,” so store both ratio and percent form.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
4.  **Price distribution assumption**
    -   The paper models prices as lognormal with mean and variance set to the base price and price volatility, respectively.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
    -   In a data spec context, this means you must compute sample means and variances of the price variable (e.g., price ratio) over the historical period for use as lognormal parameters.

**3.2 Futures data sources and extraction**

You need a consistent historical series of December CBOT corn futures prices.

1.  **Sources (examples)**
    -   Commercial/website data (Barchart, TradingCharts, Investing.com, CME archives) provide historical daily futures prices for corn (symbol ZC, previously C).[barchart]
    -   For a research-grade dataset, you may prefer:
        -   CME or a data vendor (e.g., Quandl/Nasdaq, Refinitiv, Bloomberg, CRB) via institutional subscriptions.
2.  **Contracts to include**
    -   December contract of each crop year:
        -   Identify the December CBOT corn futures contract expiring in December of year $$t$$(symbol changes over time but conceptually the same).
3.  **Daily prices**
    -   Extract daily settlement/close prices (USD per bushel) for each December contract.
    -   Required fields:
        -   Contract identifier.
        -   Trade date.
        -   Settlement or close price.
        -   Volume/open interest (optional, but useful for QC).
4.  **Base and harvest price calculation**
    -   For each year $$t$$:
        -   Base price:
            -   Filter to all trading days in February of year $$t$$for the December $$t$$contract.
            -   Compute arithmetic mean of settlement prices:
                -   $$\text{BasePrice}_{t} = \frac{1}{N_{F}} \sum_{d \in \text{Feb} ( t )}^{} P_{d , t}^{D e c}$$.
        -   Harvest price:
            -   Filter to all trading days in October of year $$t$$for the same contract.
            -   Compute arithmetic mean:
                -   $$\text{HarvestPrice}_{t} = \frac{1}{N_{O}} \sum_{d \in \text{Oct} ( t )}^{} P_{d , t}^{D e c}$$.
    -   Ensure trading calendar alignment (exclude holidays, weekends naturally handled by missing days).
5.  **Period coverage**
    -   Dataset 1:
        -   Compute base and harvest prices for 1975–2009.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
        -   Confirm actual available futures history; many public sources give continuous data reliably from \~1980 onward; for earlier years, you may need a vendor or archival source.
    -   Dataset 2:
        -   Extend base and harvest prices through latest available year (e.g., 2025 or 2026).
6.  **Quality checks**
    -   Plot base and harvest prices over time to ensure no obvious discontinuities.
    -   Compare to USDA/ERS published corn price series (e.g., Feed Grains Yearbook) for sanity.[ers.usda]

**4. Insurance and revenue variables**

The paper focuses on GRIP (Group Risk Income Protection) for county revenue.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]

**4.1 County revenue**

1.  **Definition**
    -   County revenue in year $$t$$:
        -   $$\text{Revenue}_{c , t} = Y_{c , t} \times \text{HarvestPrice}_{t}$$,
        -   where $$Y_{c , t}$$is (possibly detrended) county yield.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
2.  **APH yield**
    -   APH (Actual Production History) yield approximated by mean county yield:
        -   $$\text{APH}_{c} = \frac{1}{T_{c}} \sum_{t}^{} Y_{c , t}$$over baseline years, following RMA or paper’s practice.
    -   The paper treats APH as the mean yield of each county.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]

**4.2 Coverage levels and guarantee**

1.  **Coverage levels**
    -   Coverage factors $$\text{Cov} \in \left\{ 0 . 6 5 \right\}$$.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
2.  **Guarantee revenue**
    -   For GRIP-HR, guarantee can adjust with harvest price; the paper gives formulas:
        -   Indemnity for GRIP-HR:
            -   $$\text{Indemnity}_{c , t} = \max ( 0 )$$.[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]
        -   Document the exact formula you implement; for data storage, you can store:
            -   guarantee_hr_ct (per county-year-coverage).
            -   indemnity_hr_ct.

**5. Yield–price joint data for copula estimation**

You want a dataset that can feed directly into copula fitting and mixture estimation.

**5.1 Dataset 1 (replication: 1975–2009)**

1.  **Observation unit**
    -   County–year pairs for 1975–2009, restricted to years where both yield and price data are available.
2.  **Variables for copula**
    -   yield_raw_ct: observed yield.
    -   yield_trend_ct: predicted yield from linear trend.
    -   yield_resid_ct: $$y_{c , t} - \widehat{y}_{c , t}$$or ratio, per your choice.
    -   price_base_t: base price (Feb average, Dec futures).
    -   price_harvest_t: harvest price (Oct average).
    -   price_ratio_t: price_harvest_t / price_base_t.
    -   price_pctchg_t: (price_harvest_t - price_base_t)/price_base_t.
    -   revenue_ct: yield_raw_ct \* price_harvest_t.
    -   APH_c: mean yield for county.
    -   For each coverage level cov:
        -   guarantee_hr_ct_cov.
        -   indemnity_hr_ct_cov.
3.  **Panel structure**
    -   Ensure each county has the same number of years (ideally 1975–2009); document any missing.
4.  **Prepared inputs for CML**
    -   For subsequent copula estimation, you will convert yields and prices to pseudo-observations via empirical CDFs; but for the data spec, just ensure each county’s yield and the common price variable are present and aligned.

**5.2 Dataset 2 (extended period)**

1.  **Extended years**
    -   Add years beyond 2009 through the latest available (e.g., 2010–2025).
    -   Optionally also include pre-1975 data if NASS and futures history permit; label as pre-study extension.
2.  **Same variable definitions**
    -   Use exactly the same definitions and transformations as Dataset 1 for all variables.
    -   Refit trends as described in Section 2.2; you might provide two trend versions:
        -   Trend fitted on 1975–2009.
        -   Trend fitted on full 1975–latest.
3.  **Dataset labeling**
    -   Include a variable dataset_version:
        -   "original_window_1975_2009" for years 1975–2009 with trends fitted on that window.
        -   "extended_window" for years beyond 2009 (and/or pre-1975) and possibly trends fitted on the full sample.

**6. Alignment and consistency**

**6.1 Aligning yield and price years**

1.  **Consistency requirement**
    -   For year $$t$$, county yield $$Y_{c , t}$$must correspond to the same crop marketing year as the December futures contract used in base/harvest prices.
    -   Confirm NASS’s yield year definition (harvest year) aligns with CBOT contract year.
2.  **Checks**
    -   For each year, compute correlation between detrended yields and price ratio/percentage change to ensure plausible relationships.
    -   Visual checks: yield distributions by year; price distributions by year.

**6.2 Matching to original sample**

To mimic their 602-county sample:[paper: Efficient_Estimation_of_Copula_Mixture_M.pdf]

1.  **Sample restriction**
    -   Exclude counties with fewer than 35 observations over 1975–2009.
    -   Exclude counties with missing or suppressed yields for substantial portions of the period.
    -   Document sample selection rules explicitly.
2.  **Comparison metrics**
    -   Summary statistics (mean, variance) of yields and price changes.
    -   Compare approximate yield and price series to those implied by their reported insurance rates or other companion papers (e.g., Woodard & Sherrick) where possible.

**7. Data products and files**

Define deliverables for yourself/RA:

1.  **Core panel datasets**
    -   corn_grip_panel_1975_2009.parquet (or CSV):
        -   All variables in Section 5.1.
    -   corn_grip_panel_extended.parquet:
        -   All variables 1975–latest, with dataset_version flag.
2.  **Auxiliary tables**
    -   county_trend_params.csv:
        -   state_fips, county_fips, alpha_c, beta_c, n_obs, trend_window.
    -   price_summary.csv:
        -   Year-level base/harvest prices, price_ratio, price_pctchg.
    -   aph_table.csv:
        -   County-level APH values and coverage-level guarantees for baseline.
3.  **Metadata / codebook**
    -   Document every variable with:
        -   Name, type, units, definition, source, and formula.

**8. Optional extensions for your research**

Given your interests in synthetic data and copulas, you may want additional fields:

1.  **Climate / weather covariates**
    -   County-level precipitation/temperature aggregates by growing season to allow climate–yield copula extensions.
2.  **Scenario flags**
    -   Indicators for major drought years (e.g., 1988, 2012) for robustness checks.
3.  **Standardized residuals**
    -   $$\widehat{\varepsilon}_{c , t} / \widehat{\sigma}_{c}$$for yields, to improve comparability across counties.
