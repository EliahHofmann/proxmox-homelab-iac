"""Die CA-Dateien im Repo muessen Python 3.13 genuegen (VERIFY_X509_STRICT verlangt keyUsage)."""
import shutil
import subprocess
from pathlib import Path

import pytest

FILES = Path(__file__).resolve().parents[2] / "ansible" / "files"


@pytest.mark.parametrize("name", ["pve-root-ca.pem", "vault-ca.pem"])
def test_ca_hat_key_usage_fuer_zertifikate(name):
    if not shutil.which("openssl"):
        pytest.skip("openssl fehlt")
    out = subprocess.run(["openssl", "x509", "-in", str(FILES / name), "-noout", "-ext", "keyUsage,basicConstraints"],
                         capture_output=True, text=True, check=True).stdout
    assert "CA:TRUE" in out
    assert "Certificate Sign" in out
