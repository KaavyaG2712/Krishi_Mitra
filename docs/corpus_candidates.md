# Initial Agronomy Advisor corpus candidates

These are authoritative, public starting points identified for Review 3. Before ingestion, a team member must download the exact source, record its checksum and accessed date, inspect page extraction quality, and confirm each chunk does not provide an unsafe standalone pesticide dosage. The advisor will cite pages and will refer safety-critical situations to a KVK or agricultural officer.

| Crop/topic | Candidate source | Publisher | Why it is useful |
| --- | --- | --- | --- |
| Tomato | [ICAR Kharif Agro-Advisory 2025](https://www.icar.gov.in/sites/default/files/Circulars/ICAR%20En-Kharif%20Agro-Advisories%20for%20Farmers%202025.pdf) | ICAR | Tomato cultivation and early/late blight context. |
| Tomato | [Tomato field demonstration and blight-management context](https://icar.gov.in/en/node/4685) | ICAR / KVK Dehradun | Context on spacing, canopy management, and early/late blight risk. |
| Potato | [ICAR Rabi Agro-Advisory for Farmers](https://www.icar.gov.in/en/icar-rabi-agro-advisory-farmers-0) | ICAR | Potato and blight-related advisory material. |
| Potato | [ICAR Kharif Agro-Advisory 2025](https://www.icar.gov.in/sites/default/files/Circulars/ICAR%20En-Kharif%20Agro-Advisories%20for%20Farmers%202025.pdf) | ICAR | Potato growing and disease-prevention context. |
| Maize | [ICAR Crop Science: Maize](https://icar.gov.in/en/crop-science/maize) | ICAR | Official maize crop reference; supplement with a maize-specific extension bulletin before ingestion. |
| Maize | [ICAR Annual Report 2022–23](https://www.icar.gov.in/sites/default/files/2025-04/ICAR-Annual-Report-2022-23-English.pdf) | ICAR | References maize common rust and disease research. |
| Grape | [ICAR Sixth Deans' Committee report](https://icar.gov.in/sites/default/files/2026-06/SIXTH%20DEANS%20COMMITTEE%20VOL%201%20FINAL%207-3-2026.pdf) | ICAR | Crop-disease curriculum reference; replace or supplement with a grape extension bulletin that specifically addresses black rot. |
| Cross-crop safety | [ICAR Selected Agricultural Technologies compendium](https://icar.gov.in/en/selected-agricultural-technologies-compendium) | ICAR | General reference candidate for integrated practices and safety framing. |

## Before the ingestion phase

1. Expand this list to 10–12 final documents, including at least two suitable sources per supported crop and two cross-crop IPM/safety sources.
2. Prefer source PDFs with stable URLs and explicit page numbers.
3. Store local downloads outside Git, in `data/raw/corpus/`.
4. Add title, publisher, source URL, access date, licence/terms, SHA-256 checksum, crops, topics, and relevant pages to the final corpus register.
