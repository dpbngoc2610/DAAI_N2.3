from __future__ import annotations

import argparse
import ssl
from pathlib import Path

import certifi


def build(output: Path) -> int:
    certifi_payload = Path(certifi.where()).read_text(encoding="ascii")
    seen = {
        block.strip()
        for block in certifi_payload.split("-----END CERTIFICATE-----")
        if "BEGIN CERTIFICATE" in block
    }
    blocks = [certifi_payload.rstrip()]
    added = 0
    for store in ("ROOT", "CA"):
        for certificate, encoding, _trust in ssl.enum_certificates(store):
            if encoding != "x509_asn":
                continue
            pem = ssl.DER_cert_to_PEM_cert(certificate).strip()
            if pem not in seen:
                seen.add(pem)
                blocks.append(pem)
                added += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(blocks) + "\n", encoding="ascii")
    print(f"windows_ca_bundle={output}")
    print(f"windows_certificates_added={added}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge certifi and the Windows certificate stores.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return build(args.output.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
