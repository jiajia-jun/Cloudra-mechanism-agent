# Cloudra research data

Public read-only study-data directory: https://drive.google.com/drive/folders/1yZo3eJuCUuAgedQztgCtLyJcc8MZipf7

Release registration: 1 November 2026. The original package names and version dates are retained.

## Packages

| Package | Contents | Download |
| --- | --- | --- |
| P2 full campaign, version 20261031 | 50 tasks, four workflow configurations, 200 retained runs; result tables, offline-organization provenance, campaign databases, sandboxes, native calculation outputs, runtime records, and configuration snapshots. The full archive includes the 3-run pilot and 197-run main campaign. | [Cloudra-P2-final-20261031-FULL.tar.gz](https://drive.google.com/file/d/1DXtlUEmhshADrG48fyZLkEuqNxFWOTFM/view?usp=drivesdk) |
| P1b repeated-task study, version 20261024 with 20261025 supplement | 48 runs; original campaign, historical rescoring supplement, and subsequent offline-organization records. | [P1b folder](https://drive.google.com/drive/folders/1UIrzVTqZg8RofJcWX_dlhN-EoqpfkBjg) |
| Gold evidence, version 20261018-d10056e7-drive1 | Reference calculation inputs, native outputs, geometries, Hessians, task definitions, provenance, and a standalone verification script. | [Gold evidence ZIP](https://drive.google.com/file/d/15YDa_ycWoLUANPsDdQ1rUOiNp_-wqOs5/view?usp=drivesdk) |
| SI companion data, revision 20261031 | 50 task definitions; all 200 formal composites and 600 score components at source precision; timing, behavioral and activation records; literature register; figure/table reproduction scripts. | [Cloudra_SI_Data.zip](https://drive.google.com/file/d/1rxeg3nLczQyiO6ZackLq-LeTxzcsxHrL/view?usp=drivesdk) |
| Complete behavioral-source archive, version 20261030 | Frozen prompts/responses, activation states and logits, readable event traces, original source databases and calculation records, figure/analysis materials, and archived manuscript context for Sections 3.2–3.3. Three ZIPs total 164,708,050 bytes. | [Behavioral and activation-source folder](https://drive.google.com/drive/folders/1Zkn6_2aDlloAe-bmfd7w27zxmQKj5L9K) |

P2 upload is complete. Its cloud file size matches the original 14,915,315,627-byte archive, and public read-only access is verified.

The P2 archive is 14,915,315,627 bytes compressed and contains 195,453 regular files, with 48,488,766,289 bytes of file content after decompression. `P2_PACKAGE_INVENTORY.json` records the package-level inventory and the 200-row retained-run composition.

## Verification and use

`SHA256SUMS.txt` provides whole-package checksums for the P2, Gold, and SI packages. The P1b and behavioral-source folders each provide a checksum table for their three packages. Download the relevant packages and checksum table to the same directory, then use `shasum -a 256 -c SHA256SUMS.txt` to verify the downloaded bytes. Individual archives also retain their internal inventories and provenance records.

Unpack `Cloudra_SI_Data.zip` beside the SI typesetting project to obtain `companion_data/`. Publication reproduction instructions are in SI Section S7 and `companion_data/publication_reproduction/`. They reconstruct the retained tables and figures from archived records without launching new agent or quantum-chemical calculations.

The P2 result tables, original run records, and P1b historical and later offline-organized results retain their individual version labels. Use the corresponding publication tables and provenance records for each study.

Scientific methods, permitted calculations, scoring definitions, and interpretation are described in the manuscript, SI, and the package-specific documentation. Public data access is separate from software release and does not alter the software licensing or manuscript version.
