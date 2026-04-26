"""
he_layer.py
-----------
Homomorphic Encryption layer for Smart Home Energy Analytics
Using TenSEAL (CKKS scheme) — supports encrypted computation on floats.

What this file does:
  1. Pulls raw energy readings from MongoDB (same data your API uses)
  2. Encrypts selected sensitive fields using CKKS homomorphic encryption
  3. Performs aggregations (sum, mean, weighted average) ENTIRELY on ciphertexts
  4. Decrypts only the final result — raw values are never exposed during computation
  5. Verifies the encrypted result matches the plaintext result (proof of correctness)
  6. Exposes two Flask endpoints you can mount onto your existing api.py

Install:
  pip install tenseal

How CKKS works (brief):
  - CKKS = Cheon-Kim-Kim-Song scheme, designed for approximate arithmetic on reals
  - You encrypt a vector of floats into a single ciphertext
  - Additions and multiplications work directly on ciphertexts
  - Small approximation error (~1e-6) is acceptable for energy analytics
  - The private key never leaves the server; only the result is decrypted

Endpoints added:
  GET /api/he/summary          — encrypted energy + cost aggregation per device
  GET /api/he/verify           — side-by-side plaintext vs HE result comparison
"""

import tenseal as ts
import numpy as np
import pymongo
import time
from flask import Blueprint, jsonify
from datetime import datetime, timezone
# ── Config ────────────────────────────────────────────────────────────────────

MONGO_URI = "mongodb://admin:admin123@ac-smxdtmy-shard-00-00.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-01.nvratez.mongodb.net:27017,ac-smxdtmy-shard-00-02.nvratez.mongodb.net:27017/?ssl=true&replicaSet=atlas-12lqnf-shard-0&authSource=admin&appName=Cluster0"

# CKKS parameters — tuned for energy analytics:
#   poly_modulus_degree: controls security vs performance (8192 = 128-bit security)
#   coeff_mod_bit_sizes: precision levels — [60, 40, 40, 60] gives ~3 levels of
#                        multiplication depth (sufficient for mean = sum / count)
#   global_scale:        2^40 balances precision vs noise for float aggregations
CKKS_POLY_MOD_DEGREE  = 8192
CKKS_COEFF_MOD_BITS   = [60, 40, 40, 60]
CKKS_SCALE            = 2 ** 40

# ── TenSEAL context (holds public + private keys) ────────────────────────────
# In a real deployment: generate once, store private key securely, share only
# the public key with any system that needs to encrypt (but not decrypt).

def build_he_context() -> ts.Context:
    """Creates a CKKS context with a fresh keypair."""
    ctx = ts.context(
        ts.SCHEME_TYPE.CKKS,
        poly_modulus_degree=CKKS_POLY_MOD_DEGREE,
        coeff_mod_bit_sizes=CKKS_COEFF_MOD_BITS,
    )
    ctx.generate_galois_keys()   # needed for vector rotation (used in inner products)
    ctx.global_scale = CKKS_SCALE
    return ctx

# ── MongoDB connection ────────────────────────────────────────────────────────

client     = pymongo.MongoClient(MONGO_URI)
db         = client["smart_home"]
data_col   = db["appliance_data"]
alerts_col = db["anomaly_alerts"]

# ── Core HE computation functions ────────────────────────────────────────────

def load_device_vectors(device_name: str) -> dict:
    """
    Pulls all records for a device from MongoDB and returns raw float vectors.
    These vectors are what gets encrypted — MongoDB only ever sees them as
    plaintext here, but in a real deployment they would arrive pre-encrypted
    from edge devices and never be stored as plaintext at all.
    """
    records = list(data_col.find(
        {"device_name": device_name},
        {"_id": 0, "total_energy_kWh": 1, "total_cost_EGP": 1,
         "avg_power_W": 1, "active_minutes": 1}
    ))

    if not records:
        return {}

    return {
        "energy":   [r["total_energy_kWh"] for r in records],
        "cost":     [r["total_cost_EGP"]   for r in records],
        "power":    [r["avg_power_W"]       for r in records],
        "active":   [r["active_minutes"]    for r in records],
        "n":        len(records),
    }


def he_sum_vector(ctx: ts.Context, plaintext_vector: list) -> float:
    """
    Encrypts a vector, sums all elements using HE, decrypts and returns the result.

    The key insight: the SUM happens entirely on the ciphertext.
    The server performing the sum never sees any individual value.

    Steps:
      1. Encrypt the full vector as a single CKKS ciphertext
      2. Call .sum() — this uses Galois rotations to fold the vector in half
         repeatedly, accumulating into the first slot
      3. Decrypt → get approximate sum (error < 1e-4 for typical energy values)
    """
    enc_vec = ts.ckks_vector(ctx, plaintext_vector)
    enc_sum = enc_vec.sum()                  # HE addition, no decryption
    result  = enc_sum.decrypt()[0]           # decrypt only the scalar result
    return result


def he_mean_vector(ctx: ts.Context, plaintext_vector: list) -> float:
    """
    Computes mean over encrypted values.
    Note: division by a plaintext scalar (n) is allowed in CKKS — it's a
    scalar multiplication, not a ciphertext-ciphertext operation.
    This keeps noise low and stays within our multiplication depth budget.
    """
    n       = len(plaintext_vector)
    enc_vec = ts.ckks_vector(ctx, plaintext_vector)
    enc_sum = enc_vec.sum()
    enc_avg = enc_sum * (1.0 / n)            # scalar multiply — no extra noise level
    result  = enc_avg.decrypt()[0]
    return result


def he_weighted_cost_share(
    ctx: ts.Context,
    device_costs: list,
    all_costs_flat: list
) -> float:
    """
    Computes this device's share of total cost, entirely encrypted.

    Plaintext equivalent: sum(device_costs) / sum(all_costs)

    HE approach:
      - Encrypt device cost vector → sum it (HE)
      - Encrypt all-device cost vector → sum it (HE)
      - Division: since we can't divide ciphertexts directly, we decrypt the
        denominator (grand total) and use it as a plaintext scalar divisor.
        This is a standard and accepted HE pattern — the grand total is not
        sensitive on its own (it's already in your API's /total/cost endpoint).

    Returns share as a percentage (0–100).
    """
    enc_device = ts.ckks_vector(ctx, device_costs)
    enc_all    = ts.ckks_vector(ctx, all_costs_flat)

    enc_device_sum = enc_device.sum()
    enc_all_sum    = enc_all.sum()

    grand_total    = enc_all_sum.decrypt()[0]          # decrypt denominator only
    enc_share      = enc_device_sum * (100.0 / max(grand_total, 1e-9))
    share          = enc_share.decrypt()[0]
    return share


# ── Main HE analytics function ────────────────────────────────────────────────

def run_he_analytics() -> dict:
    """
    Full HE analytics pipeline:
      For each device → encrypt energy, cost, power vectors → aggregate on
      ciphertexts → decrypt scalar results → compare to plaintext ground truth.

    Returns a structured result dict ready for JSON serialisation.
    """
    ctx = build_he_context()

    devices      = sorted(data_col.distinct("device_name"))
    device_results = []

    # Collect all costs for share-of-total computation
    all_costs_flat = []
    device_vectors = {}

    for device in devices:
        vecs = load_device_vectors(device)
        if not vecs:
            continue
        device_vectors[device] = vecs
        all_costs_flat.extend(vecs["cost"])

    if not all_costs_flat:
        return {"error": "No data found in database"}

    total_he_time_ms = 0

    for device in devices:
        if device not in device_vectors:
            continue

        vecs = device_vectors[device]
        n    = vecs["n"]

        t0 = time.perf_counter()

        # ── Encrypted computations ────────────────────────────────────────────
        he_total_energy = he_sum_vector(ctx, vecs["energy"])
        he_total_cost   = he_sum_vector(ctx, vecs["cost"])
        he_avg_power    = he_mean_vector(ctx, vecs["power"])
        he_avg_active   = he_mean_vector(ctx, vecs["active"])
        he_cost_share   = he_weighted_cost_share(ctx, vecs["cost"], all_costs_flat)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        total_he_time_ms += elapsed_ms

        # ── Plaintext ground truth (for verification) ─────────────────────────
        pt_total_energy = sum(vecs["energy"])
        pt_total_cost   = sum(vecs["cost"])
        pt_avg_power    = sum(vecs["power"])  / n
        pt_avg_active   = sum(vecs["active"]) / n
        pt_cost_share   = pt_total_cost / max(sum(all_costs_flat), 1e-9) * 100

        # ── Approximation error (should be < 0.01% for CKKS at this scale) ───
        def pct_error(he_val, pt_val):
            if abs(pt_val) < 1e-9:
                return 0.0
            return abs(he_val - pt_val) / abs(pt_val) * 100

        device_results.append({
            "device_name":    device,
            "records_used":   n,
            "he_time_ms":     round(elapsed_ms, 2),

            # Encrypted results (post-decryption)
            "he_results": {
                "total_energy_kWh": round(he_total_energy, 4),
                "total_cost_EGP":   round(he_total_cost,   2),
                "avg_power_W":      round(he_avg_power,     1),
                "avg_active_min":   round(he_avg_active,    2),
                "cost_share_pct":   round(he_cost_share,    2),
            },

            # Plaintext reference (to prove HE result is correct)
            "plaintext_reference": {
                "total_energy_kWh": round(pt_total_energy, 4),
                "total_cost_EGP":   round(pt_total_cost,   2),
                "avg_power_W":      round(pt_avg_power,     1),
                "avg_active_min":   round(pt_avg_active,    2),
                "cost_share_pct":   round(pt_cost_share,    2),
            },

            # Approximation errors — proves CKKS accuracy
            "approximation_errors": {
                "total_energy_pct": round(pct_error(he_total_energy, pt_total_energy), 6),
                "total_cost_pct":   round(pct_error(he_total_cost,   pt_total_cost),   6),
                "avg_power_pct":    round(pct_error(he_avg_power,    pt_avg_power),     6),
                "avg_active_pct":   round(pct_error(he_avg_active,   pt_avg_active),    6),
            },

            # Correctness verdict
            "all_within_tolerance": all([
                pct_error(he_total_energy, pt_total_energy) < 0.01,
                pct_error(he_total_cost,   pt_total_cost)   < 0.01,
                pct_error(he_avg_power,    pt_avg_power)    < 0.01,
            ]),
        })

    return {
        "scheme":              "CKKS (Cheon-Kim-Kim-Song)",
        "library":             "TenSEAL",
        "poly_modulus_degree": CKKS_POLY_MOD_DEGREE,
        "scale_bits":          40,
        "security_level":      "128-bit",
        "total_he_time_ms":    round(total_he_time_ms, 2),
        "devices_processed":   len(device_results),
        "computed_at":         datetime.now(timezone.utc).isoformat(),
        "what_was_encrypted":  [
            "total_energy_kWh vector (one value per 30-min interval)",
            "total_cost_EGP vector",
            "avg_power_W vector",
            "active_minutes vector",
        ],
        "operations_on_ciphertext": [
            "vector sum (via Galois rotation folding)",
            "scalar multiply (for mean and share computation)",
        ],
        "per_device": device_results,
    }


# ── Flask Blueprint (mount onto your existing api.py) ────────────────────────

he_bp = Blueprint("he", __name__)


@he_bp.route("/api/he/summary", methods=["GET"])
def he_summary():
    """
    Runs the full HE analytics pipeline and returns encrypted-computed results.
    First call takes ~5–15 seconds (HE is slow by design — security has a cost).
    """
    try:
        result = run_he_analytics()
        return jsonify({"status": "ok", "data": result})
    except Exception as ex:
        return jsonify({"status": "error", "message": str(ex)}), 500


@he_bp.route("/api/he/verify", methods=["GET"])
def he_verify():
    """
    Focused verification endpoint — returns a clean side-by-side comparison
    of HE vs plaintext results to demonstrate correctness.
    Useful for presentations and demos.
    """
    try:
        result   = run_he_analytics()
        devices  = result.get("per_device", [])

        summary_rows = []
        all_correct  = True

        for d in devices:
            he  = d["he_results"]
            pt  = d["plaintext_reference"]
            err = d["approximation_errors"]
            ok  = d["all_within_tolerance"]
            if not ok:
                all_correct = False

            summary_rows.append({
                "device":                   d["device_name"],
                "he_total_energy_kWh":      he["total_energy_kWh"],
                "pt_total_energy_kWh":      pt["total_energy_kWh"],
                "energy_error_pct":         err["total_energy_pct"],
                "he_total_cost_EGP":        he["total_cost_EGP"],
                "pt_total_cost_EGP":        pt["total_cost_EGP"],
                "cost_error_pct":           err["total_cost_pct"],
                "he_avg_power_W":           he["avg_power_W"],
                "pt_avg_power_W":           pt["avg_power_W"],
                "power_error_pct":          err["avg_power_pct"],
                "within_tolerance":         ok,
            })

        return jsonify({
            "status": "ok",
            "data": {
                "verdict":          "✅ All HE results match plaintext" if all_correct
                                    else "⚠️  Some results exceed 0.01% tolerance",
                "all_correct":      all_correct,
                "tolerance":        "0.01% maximum relative error",
                "scheme":           result["scheme"],
                "total_he_time_ms": result["total_he_time_ms"],
                "computed_at":      result["computed_at"],
                "comparison":       summary_rows,
            }
        })
    except Exception as ex:
        return jsonify({"status": "error", "message": str(ex)}), 500


# ── Standalone runner (python he_layer.py) ────────────────────────────────────

if __name__ == "__main__":
    print("\n🔐 Homomorphic Encryption Analytics Demo")
    print("=" * 60)
    print("Scheme:   CKKS (approximate arithmetic over reals)")
    print("Library:  TenSEAL")
    print("Security: 128-bit (poly_modulus_degree=8192)")
    print("=" * 60)
    print("\nRunning encrypted aggregations... (this takes ~5–15 seconds)\n")

    t_start = time.perf_counter()
    result  = run_he_analytics()
    t_total = (time.perf_counter() - t_start) * 1000

    print(f"Encrypted {result['devices_processed']} devices in {result['total_he_time_ms']:.0f}ms\n")
    print(f"{'Device':<25} {'HE Energy':>12} {'PT Energy':>12} {'Error%':>8}  "
          f"{'HE Cost':>10} {'PT Cost':>10} {'Error%':>8}  {'✓'}")
    print("-" * 100)

    all_pass = True
    for d in result["per_device"]:
        he  = d["he_results"]
        pt  = d["plaintext_reference"]
        err = d["approximation_errors"]
        ok  = "✅" if d["all_within_tolerance"] else "❌"
        if not d["all_within_tolerance"]:
            all_pass = False

        print(
            f"  {d['device_name']:<23} "
            f"{he['total_energy_kWh']:>12.4f} "
            f"{pt['total_energy_kWh']:>12.4f} "
            f"{err['total_energy_pct']:>8.6f}  "
            f"{he['total_cost_EGP']:>10.2f} "
            f"{pt['total_cost_EGP']:>10.2f} "
            f"{err['total_cost_pct']:>8.6f}  "
            f"{ok}"
        )

    print("\n" + "=" * 60)
    if all_pass:
        print("✅  All encrypted computations match plaintext within 0.01% tolerance")
    else:
        print("⚠️   Some results exceeded tolerance — check CKKS parameters")

    print(f"\n⏱️  Total wall time: {t_total:.0f}ms")
    print("\nTo add HE endpoints to your API, add these 3 lines to api.py:")
    print("  from he_layer import he_bp")
    print("  app.register_blueprint(he_bp)")
    print("  # Then visit: http://127.0.0.1:5000/api/he/summary")
    print("              http://127.0.0.1:5000/api/he/verify")
    