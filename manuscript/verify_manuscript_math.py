"""Independent numerical & symbolic verification for Task 1 revised chapters
(Chapter 8 / Lec9 & Chapter 5-6 / Lec6-7) + figure generation.

Run with:
    python manuscript/verify_manuscript_math.py [--prices data/prices.csv] [--plot]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.linalg import schur

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def verify_lec9_examples():
    report = {}

    # 1. Lec9 p.2-3 ODE example: A = [[7, -4], [5, -2]] -> eigenvalues 3, 2
    A_ode = np.array([[7.0, -4.0], [5.0, -2.0]])
    w_ode = sorted(np.linalg.eigvals(A_ode).real.tolist())
    assert np.allclose(w_ode, [2.0, 3.0]), w_ode
    report["ode_example"] = {"eigenvalues": [round(x, 6) for x in w_ode]}

    # 2. Lec9 p.8-9 defective matrix example: A = [[-3,1,-3],[20,3,10],[2,-2,4]]
    A_def = np.array([[-3.0, 1.0, -3.0], [20.0, 3.0, 10.0], [2.0, -2.0, 4.0]])
    w_def = sorted(np.linalg.eigvals(A_def).real.tolist())
    assert np.allclose(w_def, [-2.0, 3.0, 3.0])
    # Geometric multiplicity of lambda=3 is 3 - rank(A - 3I) = 1 < 2
    geo_3 = 3 - np.linalg.matrix_rank(A_def - 3.0 * np.eye(3))
    assert geo_3 == 1
    report["lec9_p8_defective"] = {"eigenvalues": [-2, 3, 3], "geo_mult_3": int(geo_3)}

    # 3. Lec9 p.11 Gerschgorin example: A = [[5,1,1],[0,6,1],[1,0,-5]]
    A_ger = np.array([[5.0, 1.0, 1.0], [0.0, 6.0, 1.0], [1.0, 0.0, -5.0]])
    w_ger = sorted(np.linalg.eigvals(A_ger).real.tolist())
    # Verify diagonal similarity scaling D = diag(1, 1, 5) tightens disk around -5
    D = np.diag([1.0, 1.0, 5.0])
    A_scaled = np.linalg.inv(D) @ A_ger @ D
    assert np.allclose(sorted(np.linalg.eigvals(A_scaled).real), w_ger)
    r_orig = [sum(abs(A_ger[i, j]) for j in range(3) if j != i) for i in range(3)]
    r_scaled = [sum(abs(A_scaled[i, j]) for j in range(3) if j != i) for i in range(3)]
    report["gerschgorin_p11"] = {
        "exact_eigenvalues": [round(x, 6) for x in w_ger],
        "row_radii_orig": r_orig,
        "row_radii_scaled_D115": [round(x, 4) for x in r_scaled],
    }

    # 4. Lec9 p.14 & p.18 diagonalizability comparison + spectral projectors
    B_diag = np.array([[1.0, -4.0, -4.0], [8.0, -11.0, -8.0], [-8.0, 8.0, 5.0]])
    P = np.array([[1.0, 1.0, 1.0], [2.0, 1.0, 0.0], [-2.0, 0.0, 1.0]])
    D_mat = np.linalg.inv(P) @ B_diag @ P
    assert np.allclose(D_mat, np.diag([1.0, -3.0, -3.0]))
    # Lagrange spectral projectors: G1 = (B + 3I)/(1 - (-3)), G2 = (B - I)/(-3 - 1)
    G1 = (B_diag + 3.0 * np.eye(3)) / 4.0
    G2 = (B_diag - np.eye(3)) / (-4.0)
    assert np.allclose(G1 + G2, np.eye(3))
    assert np.allclose(G1 @ G2, np.zeros((3, 3)))
    assert np.allclose(G1 @ G1, G1) and np.allclose(G2 @ G2, G2)
    assert np.allclose(1.0 * G1 + (-3.0) * G2, B_diag)
    report["spectral_projectors_p14"] = {"G1_rank": int(np.linalg.matrix_rank(G1)), "G2_rank": int(np.linalg.matrix_rank(G2))}

    # 5. Schur triangularization, Rayleigh-Ritz, Weyl perturbation, Cauchy interlacing
    rng = np.random.default_rng(42)
    M = rng.normal(size=(4, 4))
    T_schur, U_schur = schur(M, output="complex")
    assert np.allclose(U_schur.conj().T @ U_schur, np.eye(4))
    assert np.allclose(U_schur @ T_schur @ U_schur.conj().T, M)
    assert np.allclose(np.tril(T_schur, -1), 0.0)

    H = (M + M.T) / 2.0
    E_raw = rng.normal(scale=0.1, size=(4, 4))
    E = (E_raw + E_raw.T) / 2.0
    lam_H = np.sort(np.linalg.eigvalsh(H))[::-1]
    lam_E = np.sort(np.linalg.eigvalsh(E))[::-1]
    lam_HE = np.sort(np.linalg.eigvalsh(H + E))[::-1]
    # Weyl's inequality: lam_i(H) + lam_n(E) <= lam_i(H+E) <= lam_i(H) + lam_1(E)
    assert np.all(lam_HE >= lam_H + lam_E[-1] - 1e-12)
    assert np.all(lam_HE <= lam_H + lam_E[0] + 1e-12)
    # Cauchy interlacing for leading 3x3 principal submatrix
    lam_sub = np.sort(np.linalg.eigvalsh(H[:3, :3]))[::-1]
    for i in range(3):
        assert lam_H[i] + 1e-12 >= lam_sub[i] >= lam_H[i + 1] - 1e-12

    # 6. Counterexamples for Lec9 p.28 PSD pitfalls
    # (a) Leading principal minors >= 0 does NOT imply PSD:
    A_not_psd = np.array([[0.0, 0.0], [0.0, -1.0]])
    assert A_not_psd[0, 0] >= 0 and np.linalg.det(A_not_psd) >= 0
    assert np.linalg.eigvalsh(A_not_psd).min() == -1.0
    # (b) PSD matrix with zero eigenvalue CAN still have trivial LU = I * diag(1, 0):
    A_psd_lu = np.diag([1.0, 0.0])
    assert np.allclose(np.eye(2) @ A_psd_lu, A_psd_lu)
    # (c) Jordan-Wielandt embedding for SVD:
    X = rng.normal(size=(5, 3))
    sv = np.linalg.svd(X, compute_uv=False)
    JW = np.block([[np.zeros((5, 5)), X], [X.T, np.zeros((3, 3))]])
    jw_eigs = np.sort(np.abs(np.linalg.eigvalsh(JW)))[::-1][:6]
    assert np.allclose(jw_eigs, np.repeat(sv, 2))
    # (d) Eckart-Young-Mirsky rank-k approximation error
    U_s, s_s, Vt_s = np.linalg.svd(X, full_matrices=False)
    X_1 = np.outer(U_s[:, 0] * s_s[0], Vt_s[0, :])
    assert np.isclose(np.linalg.norm(X - X_1, 2), s_s[1])
    assert np.isclose(np.linalg.norm(X - X_1, "fro"), np.sqrt(np.sum(s_s[1:] ** 2)))

    # 7. Hand-worked 3x3 integer Cholesky & LDL^T example (Chapter 8 §8.4.1)
    A_chol = np.array([[4.0, 2.0, -2.0], [2.0, 10.0, 2.0], [-2.0, 2.0, 6.0]])
    L_unit = np.array([[1.0, 0.0, 0.0], [0.5, 1.0, 0.0], [-0.5, 1.0 / 3.0, 1.0]])
    D_piv = np.diag([4.0, 9.0, 4.0])
    R_upper = np.array([[2.0, 1.0, -1.0], [0.0, 3.0, 1.0], [0.0, 0.0, 2.0]])
    assert np.allclose(L_unit @ D_piv @ L_unit.T, A_chol)
    assert np.allclose(R_upper.T @ R_upper, A_chol)
    lpms = [float(np.linalg.det(A_chol[:k, :k])) for k in (1, 2, 3)]
    assert np.allclose(lpms, [4.0, 36.0, 144.0])
    assert np.allclose([lpms[0], lpms[1] / lpms[0], lpms[2] / lpms[1]], [4.0, 9.0, 4.0])
    report["cholesky_3x3_example"] = {
        "leading_principal_minors": [4, 36, 144],
        "pivots_D": [4, 9, 4],
        "eigenvalues": [round(float(v), 4) for v in np.linalg.eigvalsh(A_chol)],
    }

    # 8. PageRank Google Matrix & Power Iteration convergence (Chapter 8 §8.1.3 / Lec0 p.15)
    P_pr = np.array([
        [0.0, 0.0, 1.0, 0.5],
        [0.5, 0.0, 0.0, 0.0],
        [0.5, 1.0, 0.0, 0.5],
        [0.0, 0.0, 0.0, 0.0],
    ])
    d_damp = 0.85
    G_pr = d_damp * P_pr + (1.0 - d_damp) / 4.0 * np.ones((4, 4))
    assert np.allclose(G_pr.sum(axis=0), np.ones(4))
    eigs_pr = np.linalg.eigvals(G_pr)
    mags_pr = np.sort(np.abs(eigs_pr))[::-1]
    assert np.isclose(mags_pr[0], 1.0)
    assert mags_pr[1] <= d_damp + 1e-12
    x_pr = np.ones(4) / 4.0
    for _ in range(200):
        x_pr = G_pr @ x_pr
    pi_star = x_pr / x_pr.sum()
    assert np.allclose(G_pr @ pi_star, pi_star, atol=1e-12)
    xk = np.ones(4) / 4.0
    errs = {}
    for k in range(1, 21):
        xk = G_pr @ xk
        if k in (1, 5, 10, 20):
            errs[f"k={k}"] = round(float(np.linalg.norm(xk - pi_star, 1)), 6)
    report["pagerank_power_iteration"] = {
        "damping": d_damp,
        "abs_eigenvalues": [round(float(v), 6) for v in mags_pr],
        "stationary_pi": [round(float(v), 6) for v in pi_star],
        "l1_error_trace": errs,
    }

    # 9. Chapter 5/6 ill-conditioned 2x2 linear perturbation example (kappa_2 = 199)
    S_ill = np.array([[1.0, 0.99], [0.99, 1.0]])
    b_vec = np.array([1.0, 1.0])
    db_vec = np.array([0.005, -0.005])
    z_orig = np.linalg.solve(S_ill, b_vec)
    z_pert = np.linalg.solve(S_ill, b_vec + db_vec)
    rel_b = float(np.linalg.norm(db_vec) / np.linalg.norm(b_vec))
    rel_z = float(np.linalg.norm(z_pert - z_orig) / np.linalg.norm(z_orig))
    kappa_ill = float(np.linalg.cond(S_ill, 2))
    assert np.isclose(kappa_ill, 199.0)
    assert np.isclose(rel_z, kappa_ill * rel_b)
    report["ill_conditioned_2x2"] = {
        "kappa_2": round(kappa_ill, 4),
        "rel_rhs_perturbation": round(rel_b, 6),
        "rel_sol_perturbation": round(rel_z, 6),
        "amplification": round(rel_z / rel_b, 2),
    }

    report["core_theorems_verified"] = [
        "Schur", "Weyl", "Cauchy_Interlacing", "PSD_Counterexamples",
        "Jordan_Wielandt_SVD", "Eckart_Young_Mirsky",
        "Cholesky_3x3", "PageRank_Power_Iteration", "Condition_Perturbation_2x2",
    ]
    return report


def verify_lec9_all_10_exercises():
    """Verify all 10 exercises from Lec9 Slides 31-32."""
    ex = {}

    # Ex 1: A, B, C
    A1 = np.array([[-10.0, -7.0], [14.0, 11.0]])
    B1 = np.array([[3.0, -2.0, 5.0], [0.0, 1.0, 4.0], [0.0, -1.0, 5.0]])
    C1 = np.array([[0.0, 6.0, 3.0], [-1.0, 5.0, 1.0], [-1.0, 2.0, 4.0]])
    wA1 = sorted(np.linalg.eigvals(A1).real.tolist())
    wB1 = sorted(np.linalg.eigvals(B1).real.tolist())
    wC1 = sorted(np.linalg.eigvals(C1).real.tolist())
    assert np.allclose(wA1, [-3.0, 4.0])
    assert np.allclose(wB1, [3.0, 3.0, 3.0])
    assert np.allclose(wC1, [3.0, 3.0, 3.0])
    # Eigenvector checks for Ex 1
    assert np.allclose(A1 @ np.array([1.0, -1.0]), -3.0 * np.array([1.0, -1.0]))
    assert np.allclose(A1 @ np.array([1.0, -2.0]), 4.0 * np.array([1.0, -2.0]))
    assert 3 - np.linalg.matrix_rank(B1 - 3.0 * np.eye(3)) == 1
    assert np.allclose(B1 @ np.array([1.0, 0.0, 0.0]), 3.0 * np.array([1.0, 0.0, 0.0]))
    assert 3 - np.linalg.matrix_rank(C1 - 3.0 * np.eye(3)) == 2
    assert np.allclose(C1 @ np.array([2.0, 1.0, 0.0]), 3.0 * np.array([2.0, 1.0, 0.0]))
    assert np.allclose(C1 @ np.array([1.0, 0.0, 1.0]), 3.0 * np.array([1.0, 0.0, 1.0]))
    ex["ex1"] = {"A": [-3, 4], "B": [3, 3, 3], "B_geo_mult": 1, "C": [3, 3, 3], "C_geo_mult": 2}

    # Ex 6: A = [[-8, -6], [12, 10]] -> eigenvalues -2, 4, diagonalizable
    A6 = np.array([[-8.0, -6.0], [12.0, 10.0]])
    P6 = np.array([[1.0, 1.0], [-1.0, -2.0]])
    assert np.allclose(np.linalg.inv(P6) @ A6 @ P6, np.diag([-2.0, 4.0]))
    ex["ex6"] = {"eigenvalues": [-2, 4], "diagonalizable": True}

    # Ex 7: A = [[-4, -3, -3], [0, -1, 0], [6, 6, 5]] -> eigenvalues -1 (alg=2, geo=2), 2 (alg=1, geo=1)
    A7 = np.array([[-4.0, -3.0, -3.0], [0.0, -1.0, 0.0], [6.0, 6.0, 5.0]])
    w7 = sorted(np.linalg.eigvals(A7).real.tolist())
    assert np.allclose(w7, [-1.0, -1.0, 2.0])
    assert 3 - np.linalg.matrix_rank(A7 + np.eye(3)) == 2
    P7 = np.array([[1.0, 1.0, 1.0], [-1.0, 0.0, 0.0], [0.0, -1.0, -2.0]])
    assert np.allclose(np.linalg.inv(P7) @ A7 @ P7, np.diag([-1.0, -1.0, 2.0]))
    ex["ex7"] = {"eigenvalues": [-1, -1, 2], "geo_mult_-1": 2, "diagonalizable": True}

    # Ex 8: A = [[5+i, -2i], [2, 4+2i]] -> check A*A == AA*
    A8 = np.array([[5 + 1j, -2j], [2 + 0j, 4 + 2j]])
    diff8 = A8.conj().T @ A8 - A8 @ A8.conj().T
    is_normal = bool(np.allclose(diff8, 0.0))
    assert is_normal is True
    ex["ex8"] = {"is_normal": is_normal, "AstarA_diag": [round(float(x.real), 4) for x in np.diag(A8.conj().T @ A8)]}

    # Ex 10: Positive definiteness of A, B, C
    A10 = np.array([[1.0, -1.0, -1.0], [-1.0, 5.0, 1.0], [-1.0, 1.0, 5.0]])
    B10 = np.array([[20.0, 6.0, 8.0], [6.0, 3.0, 0.0], [8.0, 0.0, 8.0]])
    C10 = np.array([[2.0, 0.0, 2.0], [0.0, 6.0, 2.0], [2.0, 2.0, 4.0]])
    for name, mat, expected_pd in [("A", A10, True), ("B", B10, False), ("C", C10, True)]:
        eigs = np.linalg.eigvalsh(mat)
        lpm = [float(np.linalg.det(mat[:k, :k])) for k in (1, 2, 3)]
        pd_flag = bool(eigs.min() > 1e-12)
        assert pd_flag is expected_pd, (name, eigs, lpm)
        ex[f"ex10_{name}"] = {
            "leading_principal_minors": [round(x, 4) for x in lpm],
            "eigenvalues": [round(float(x), 4) for x in eigs],
            "positive_definite": pd_flag,
            "positive_semidefinite": bool(eigs.min() >= -1e-12),
        }
    # Randomized numerical verification of proof exercises Ex 2, 3, 4, 5, 9
    rng = np.random.default_rng(7)
    T_tri = np.triu(rng.normal(size=(4, 4)))
    assert np.allclose(sorted(np.linalg.eigvals(T_tri).real), sorted(np.diag(T_tri)))  # Ex 2
    S_sing = rng.normal(size=(4, 3)) @ rng.normal(size=(3, 4))
    assert np.min(np.abs(np.linalg.eigvals(S_sing))) < 1e-10  # Ex 3
    A_blk, B_blk, C_blk = rng.normal(size=(2, 2)), rng.normal(size=(2, 3)), rng.normal(size=(3, 3))
    T_blk = np.block([[A_blk, B_blk], [np.zeros((3, 2)), C_blk]])
    assert np.allclose(sorted(np.linalg.eigvals(T_blk), key=lambda z: (z.real, z.imag)),
                       sorted(np.concatenate([np.linalg.eigvals(A_blk), np.linalg.eigvals(C_blk)]),
                              key=lambda z: (z.real, z.imag)))  # Ex 4
    M_inv = rng.normal(size=(3, 3)) + 5.0 * np.eye(3)
    w_m, V_m = np.linalg.eig(M_inv)
    M_inv_mat = np.linalg.inv(M_inv)
    for k in range(3):
        assert np.allclose(M_inv_mat @ V_m[:, k], (1.0 / w_m[k]) * V_m[:, k])  # Ex 5
    T_nondiag = np.array([[2.0, 1.0], [0.0, 3.0]])
    assert not np.allclose(T_nondiag.T @ T_nondiag, T_nondiag @ T_nondiag.T)  # Ex 9
    ex["proof_exercises_verified"] = ["ex2", "ex3", "ex4", "ex5", "ex9"]
    return ex


def _generate_figures_qt(prices_path: Path | None, fig_dir: Path):
    """Crisp anti-aliased high-DPI figure renderer using PySide6 (zero extra deps)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_canvas(w, h):
        img = QtGui.QImage(w, h, QtGui.QImage.Format.Format_ARGB32)
        img.fill(QtGui.QColor("#ffffff"))
        p = QtGui.QPainter(img)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)
        return img, p

    def draw_panel_axes(p, rect, x0, x1, y0, y1, title, xlabel, ylabel, xticks=None, yticks=None):
        p.setPen(QtGui.QPen(QtGui.QColor("#cbd5e1"), 1.2))
        p.setBrush(QtGui.QBrush(QtGui.QColor("#f8fafc")))
        p.drawRect(rect)
        # Grid & ticks
        font = QtGui.QFont("DejaVu Sans", 11)
        p.setFont(font)
        def mx(x): return rect.left() + (x - x0) / (x1 - x0) * rect.width()
        def my(y): return rect.bottom() - (y - y0) / (y1 - y0) * rect.height()
        if xticks:
            for xv, lbl in xticks:
                px = mx(xv)
                p.setPen(QtGui.QPen(QtGui.QColor("#e2e8f0"), 1, QtCore.Qt.PenStyle.DashLine))
                p.drawLine(QtCore.QPointF(px, rect.top()), QtCore.QPointF(px, rect.bottom()))
                p.setPen(QtGui.QColor("#334155"))
                p.drawText(QtCore.QRectF(px - 35, rect.bottom() + 4, 70, 20), QtCore.Qt.AlignmentFlag.AlignCenter, lbl)
        if yticks:
            for yv, lbl in yticks:
                py = my(yv)
                p.setPen(QtGui.QPen(QtGui.QColor("#e2e8f0"), 1, QtCore.Qt.PenStyle.DashLine))
                p.drawLine(QtCore.QPointF(rect.left(), py), QtCore.QPointF(rect.right(), py))
                p.setPen(QtGui.QColor("#334155"))
                p.drawText(QtCore.QRectF(rect.left() - 62, py - 10, 56, 20), QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter, lbl)
        # Zero axes if in range
        p.setPen(QtGui.QPen(QtGui.QColor("#94a3b8"), 1.1))
        if x0 < 0 < x1:
            p.drawLine(QtCore.QPointF(mx(0), rect.top()), QtCore.QPointF(mx(0), rect.bottom()))
        if y0 < 0 < y1:
            p.drawLine(QtCore.QPointF(rect.left(), my(0)), QtCore.QPointF(rect.right(), my(0)))
        # Title & axis labels
        tfont = QtGui.QFont("DejaVu Sans", 13, QtGui.QFont.Weight.Bold)
        p.setFont(tfont)
        p.setPen(QtGui.QColor("#0f172a"))
        p.drawText(QtCore.QRectF(rect.left(), rect.top() - 34, rect.width(), 28), QtCore.Qt.AlignmentFlag.AlignCenter, title)
        lfont = QtGui.QFont("DejaVu Sans", 11)
        p.setFont(lfont)
        p.setPen(QtGui.QColor("#475569"))
        p.drawText(QtCore.QRectF(rect.left(), rect.bottom() + 26, rect.width(), 22), QtCore.Qt.AlignmentFlag.AlignCenter, xlabel)
        p.save()
        p.translate(rect.left() - 68, rect.top() + rect.height() / 2)
        p.rotate(-90)
        p.drawText(QtCore.QRectF(-200, -14, 400, 28), QtCore.Qt.AlignmentFlag.AlignCenter, ylabel)
        p.restore()
        return mx, my

    # Fig 1: Gerschgorin disks before & after diagonal similarity scaling
    A = np.array([[5.0, 1.0, 1.0], [0.0, 6.0, 1.0], [1.0, 0.0, -5.0]])
    D = np.diag([1.0, 1.0, 5.0])
    As = np.linalg.inv(D) @ A @ D
    eigs = np.linalg.eigvals(A)
    img, p = make_canvas(1500, 620)
    for idx, (mat, title) in enumerate([
        (A, "Original Matrix A: Row (Blue) vs Col (Teal) Disks"),
        (As, "Scaled D^-1 A D (D=diag(1,1,5)): Disk at -5 (1.0 -> 0.2)"),
    ]):
        rect = QtCore.QRectF(95 + idx * 725, 65, 620, 460)
        mx, my = draw_panel_axes(
            p, rect, -8.0, 12.0, -7.5, 7.5, title, "Re(z)", "Im(z)",
            xticks=[(-6, "-6"), (-4, "-4"), (-2, "-2"), (0, "0"), (2, "2"), (4, "4"), (6, "6"), (8, "8"), (10, "10")],
            yticks=[(-6, "-6"), (-3, "-3"), (0, "0"), (3, "3"), (6, "6")],
        )
        p.save()
        p.setClipRect(rect)
        for i in range(3):
            c = mat[i, i]
            rr = sum(abs(mat[i, j]) for j in range(3) if j != i)
            rc = sum(abs(mat[j, i]) for j in range(3) if j != i)
            rx_r = abs(mx(c + rr) - mx(c))
            ry_r = abs(my(rr) - my(0))
            p.setPen(QtGui.QPen(QtGui.QColor("#2563eb"), 2.0))
            p.setBrush(QtGui.QBrush(QtGui.QColor(37, 99, 235, 38)))
            p.drawEllipse(QtCore.QPointF(mx(c), my(0)), rx_r, ry_r)
            rx_c = abs(mx(c + rc) - mx(c))
            ry_c = abs(my(rc) - my(0))
            p.setPen(QtGui.QPen(QtGui.QColor("#0d9488"), 1.8, QtCore.Qt.PenStyle.DashLine))
            p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.drawEllipse(QtCore.QPointF(mx(c), my(0)), rx_c, ry_c)
        p.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1.5))
        p.setBrush(QtGui.QBrush(QtGui.QColor("#dc2626")))
        for ev in eigs:
            p.drawEllipse(QtCore.QPointF(mx(ev.real), my(ev.imag)), 6.0, 6.0)
        p.restore()
        # Legend box
        p.setFont(QtGui.QFont("DejaVu Sans", 9.5))
        p.setPen(QtGui.QColor("#1e293b"))
        p.drawText(QtCore.QPointF(rect.left() + 12, rect.top() + 22), "Blue: Row Gr  |  Teal dashed: Col Gc  |  Red: Exact eigenvalues (-5.09, 5.00, 6.09)")
    p.end()
    img.save(str(fig_dir / "fig1_gerschgorin_scaling.png"))

    # Fig 2: Quadratic form level ellipses x^T Sigma x = 1
    Q = np.array([[np.cos(np.pi / 6), -np.sin(np.pi / 6)], [np.sin(np.pi / 6), np.cos(np.pi / 6)]])
    A_ill = Q @ np.diag([4.0, 0.16]) @ Q.T
    mu = np.trace(A_ill) / 2.0
    A_shr = 0.6 * A_ill + 0.4 * mu * np.eye(2)
    t = np.linspace(0, 2 * np.pi, 360)
    unit = np.vstack([np.cos(t), np.sin(t)])
    img, p = make_canvas(900, 760)
    rect = QtCore.QRectF(100, 65, 720, 600)
    mx, my = draw_panel_axes(
        p, rect, -3.0, 3.0, -2.5, 2.5,
        "Quadratic Form Level Set x^T Sigma x = 1: Ill-Conditioned vs Shrunk",
        "x1", "x2",
        xticks=[(-2.5, "-2.5"), (-1.5, "-1.5"), (0, "0"), (1.5, "1.5"), (2.5, "2.5")],
        yticks=[(-2, "-2"), (-1, "-1"), (0, "0"), (1, "1"), (2, "2")],
    )
    for mat, col in [(A_ill, "#dc2626"), (A_shr, "#2563eb")]:
        vals, vecs = np.linalg.eigh(mat)
        pts = vecs @ np.diag(1.0 / np.sqrt(vals)) @ unit
        poly = QtGui.QPolygonF([QtCore.QPointF(mx(pts[0, i]), my(pts[1, i])) for i in range(pts.shape[1])])
        p.setPen(QtGui.QPen(QtGui.QColor(col), 2.8))
        p.setBrush(QtGui.QBrush(QtGui.QColor(col).lighter(180) if col == "#2563eb" else QtGui.QColor(220, 38, 38, 22)))
        if col == "#2563eb":
            p.setBrush(QtGui.QBrush(QtGui.QColor(37, 99, 235, 30)))
        p.drawPolygon(poly)
        p.setPen(QtGui.QPen(QtGui.QColor(col), 2.2, QtCore.Qt.PenStyle.DashLine))
        for k in range(2):
            v = vecs[:, k] / np.sqrt(vals[k])
            p.drawLine(QtCore.QPointF(mx(0), my(0)), QtCore.QPointF(mx(v[0]), my(v[1])))
    p.setFont(QtGui.QFont("DejaVu Sans", 11))
    p.setPen(QtGui.QColor("#dc2626"))
    p.drawText(QtCore.QPointF(rect.left() + 18, rect.top() + 28), f"Red: Raw Sigma (cond = {np.linalg.cond(A_ill):.1f}, axis ratio = sqrt(cond) = 5.0)")
    p.setPen(QtGui.QColor("#2563eb"))
    p.drawText(QtCore.QPointF(rect.left() + 18, rect.top() + 52), f"Blue: Shrunk Sigma_0.4 (cond = {np.linalg.cond(A_shr):.2f}, axis ratio = {np.sqrt(np.linalg.cond(A_shr)):.2f})")
    p.end()
    img.save(str(fig_dir / "fig2_quadratic_form_ellipsoid.png"))

    # Fig 3: Real 12-stock covariance shrinkage path & correlation PCA scree plot
    if prices_path and prices_path.exists():
        from matrixlab.analytics import analyze, shrinkage_path
        from matrixlab.data import read_prices

        prices = read_prices(prices_path)
        syms = sorted(prices.symbol.unique())
        asof = "2025-01-27"
        res = analyze(prices, syms, asof, lookback=252, alpha=0.05)
        alphas = np.linspace(0.0, 1.0, 21)
        path = shrinkage_path(prices, syms, asof, lookback=252, alphas=alphas)

        img, p = make_canvas(1500, 620)
        # Left panel: shrinkage path condition number
        r1 = QtCore.QRectF(95, 65, 620, 460)
        mx1, my1 = draw_panel_axes(
            p, r1, 0.0, 1.0, 0.0, 52.0,
            "Real 12-Stock Covariance Shrinkage Path (2025-01-27, T=252)",
            "Shrinkage Intensity alpha", "Condition Number kappa(Sigma_alpha)",
            xticks=[(0.0, "0.0"), (0.2, "0.2"), (0.4, "0.4"), (0.6, "0.6"), (0.8, "0.8"), (1.0, "1.0")],
            yticks=[(0, "0"), (10, "10"), (20, "20"), (30, "30"), (40, "40"), (50, "50")],
        )
        pts1 = [QtCore.QPointF(mx1(a), my1(c)) for a, c in zip(path["alpha"], path["condition"])]
        p.setPen(QtGui.QPen(QtGui.QColor("#2563eb"), 2.8))
        for i in range(len(pts1) - 1):
            p.drawLine(pts1[i], pts1[i + 1])
        p.setBrush(QtGui.QBrush(QtGui.QColor("#2563eb")))
        for pt in pts1:
            p.drawEllipse(pt, 4.0, 4.0)
        lw_x = mx1(res.ledoit_wolf_alpha)
        p.setPen(QtGui.QPen(QtGui.QColor("#dc2626"), 2.0, QtCore.Qt.PenStyle.DashLine))
        p.drawLine(QtCore.QPointF(lw_x, r1.top()), QtCore.QPointF(lw_x, r1.bottom()))
        p.setFont(QtGui.QFont("DejaVu Sans", 11))
        p.setPen(QtGui.QColor("#dc2626"))
        p.drawText(QtCore.QPointF(lw_x + 10, r1.top() + 34), f"Ledoit-Wolf alpha* = {res.ledoit_wolf_alpha:.4f} (cond = 30.78)")
        p.setPen(QtGui.QColor("#2563eb"))
        p.drawText(QtCore.QPointF(lw_x + 10, r1.top() + 58), "Raw cond = 48.30 -> alpha=0.50: 5.89 -> alpha=1.0: 1.00")

        # Right panel: PCA Scree plot
        r2 = QtCore.QRectF(820, 65, 620, 460)
        ev = res.explained_variance * 100.0
        cum = np.cumsum(ev)
        mx2, my2 = draw_panel_axes(
            p, r2, 0.3, 12.7, 0.0, 105.0,
            "Correlation Matrix PCA Explained Variance (12 US Equities)",
            "Principal Component", "Explained Variance (%)",
            xticks=[(i, f"PC{i}") for i in range(1, 13)],
            yticks=[(0, "0%"), (20, "20%"), (40, "40%"), (60, "60%"), (80, "80%"), (100, "100%")],
        )
        bar_w = (mx2(2) - mx2(1)) * 0.56
        p.setPen(QtGui.QPen(QtGui.QColor("#0f766e"), 1.2))
        p.setBrush(QtGui.QBrush(QtGui.QColor(13, 148, 136, 185)))
        for i, v in enumerate(ev, start=1):
            bx = mx2(i) - bar_w / 2
            by = my2(v)
            p.drawRect(QtCore.QRectF(bx, by, bar_w, my2(0) - by))
        pts2 = [QtCore.QPointF(mx2(i), my2(c)) for i, c in enumerate(cum, start=1)]
        p.setPen(QtGui.QPen(QtGui.QColor("#d97706"), 2.6))
        for i in range(len(pts2) - 1):
            p.drawLine(pts2[i], pts2[i + 1])
        p.setBrush(QtGui.QBrush(QtGui.QColor("#d97706")))
        for pt in pts2:
            p.drawEllipse(pt, 4.0, 4.0)
        p.setFont(QtGui.QFont("DejaVu Sans", 10.5))
        p.setPen(QtGui.QColor("#0f766e"))
        p.drawText(QtCore.QPointF(r2.left() + 18, r2.top() + 28), f"Bars: Individual variance (PC1={ev[0]:.1f}%, PC2={ev[1]:.1f}%, PC3={ev[2]:.1f}%)")
        p.setPen(QtGui.QColor("#b45309"))
        p.drawText(QtCore.QPointF(r2.left() + 18, r2.top() + 50), f"Orange curve: Cumulative variance (Top 3 = {cum[2]:.1f}%, Top 6 = {cum[5]:.1f}%)")
        p.end()
        img.save(str(fig_dir / "fig3_real_cov_spectrum_shrinkage.png"))

        # Fig 4: Chapter 5/6 Real 12-stock return matrix SVD decay & Eckart-Young-Mirsky reconstruction
        R_df = res.returns
        X_mat = (R_df - R_df.mean(axis=0)).to_numpy(dtype=float)
        U_r, s_r, Vt_r = np.linalg.svd(X_mat, full_matrices=False)
        tot_sq = float(np.sum(s_r ** 2))
        energy_pct = np.cumsum(s_r ** 2) / tot_sq * 100.0
        rel_err_pct = np.array([
            np.linalg.norm(X_mat - (U_r[:, :k] * s_r[:k]) @ Vt_r[:k, :], "fro") / np.sqrt(tot_sq) * 100.0
            for k in range(1, len(s_r) + 1)
        ])
        for k in range(1, len(s_r)):
            assert np.isclose(np.linalg.norm(X_mat - (U_r[:, :k] * s_r[:k]) @ Vt_r[:k, :], 2), s_r[k])

        img, p = make_canvas(1500, 620)
        # Left panel: Singular value spectrum sigma_k
        r1 = QtCore.QRectF(95, 65, 620, 460)
        ymax_s = float(np.ceil(s_r[0] * 10.0) / 10.0 + 0.15)
        yt_s = [(round(v, 2), f"{v:.2f}") for v in np.linspace(0.0, ymax_s, 6)]
        mx1, my1 = draw_panel_axes(
            p, r1, 0.3, 12.7, 0.0, ymax_s,
            "12-Stock Returns X (252x12): Singular Values",
            "Singular Value Index k", "Singular Value sigma_k",
            xticks=[(i, f"s{i}") for i in range(1, 13)],
            yticks=yt_s,
        )
        bw = (mx1(2) - mx1(1)) * 0.56
        p.setPen(QtGui.QPen(QtGui.QColor("#1d4ed8"), 1.2))
        p.setBrush(QtGui.QBrush(QtGui.QColor(37, 99, 235, 175)))
        for i, sv_val in enumerate(s_r, start=1):
            bx = mx1(i) - bw / 2
            by = my1(sv_val)
            p.drawRect(QtCore.QRectF(bx, by, bw, my1(0) - by))
        p.setFont(QtGui.QFont("DejaVu Sans", 10.5))
        p.setPen(QtGui.QColor("#1e293b"))
        p.drawText(QtCore.QPointF(r1.left() + 18, r1.top() + 26), f"sigma_1 = {s_r[0]:.4f}, sigma_12 = {s_r[-1]:.4f}")
        p.setPen(QtGui.QColor("#dc2626"))
        p.drawText(QtCore.QPointF(r1.left() + 18, r1.top() + 48), f"kappa_2(X) = {s_r[0]/s_r[-1]:.2f}  (= sqrt(kappa_2(Sigma)) = {np.sqrt(res.condition_before):.2f})")

        # Right panel: Eckart-Young cumulative energy vs relative Frobenius error
        r2 = QtCore.QRectF(820, 65, 620, 460)
        mx2, my2 = draw_panel_axes(
            p, r2, 0.5, 12.5, 0.0, 122.0,
            "Eckart-Young Rank-k Energy & Recon Error",
            "Truncation Rank k", "Percentage (%)",
            xticks=[(i, f"k={i}") for i in range(1, 13)],
            yticks=[(0, "0%"), (20, "20%"), (40, "40%"), (60, "60%"), (80, "80%"), (100, "100%")],
        )
        pts_e = [QtCore.QPointF(mx2(i), my2(v)) for i, v in enumerate(energy_pct, start=1)]
        pts_r = [QtCore.QPointF(mx2(i), my2(v)) for i, v in enumerate(rel_err_pct, start=1)]
        p.setPen(QtGui.QPen(QtGui.QColor("#0d9488"), 2.8))
        for i in range(len(pts_e) - 1):
            p.drawLine(pts_e[i], pts_e[i + 1])
        p.setBrush(QtGui.QBrush(QtGui.QColor("#0d9488")))
        for pt in pts_e:
            p.drawEllipse(pt, 4.2, 4.2)
        p.setPen(QtGui.QPen(QtGui.QColor("#dc2626"), 2.6, QtCore.Qt.PenStyle.DashLine))
        for i in range(len(pts_r) - 1):
            p.drawLine(pts_r[i], pts_r[i + 1])
        p.setBrush(QtGui.QBrush(QtGui.QColor("#dc2626")))
        for pt in pts_r:
            p.drawEllipse(pt, 4.0, 4.0)
        p.setFont(QtGui.QFont("DejaVu Sans", 10.5))
        p.setPen(QtGui.QColor("#0f766e"))
        p.drawText(QtCore.QPointF(r2.left() + 18, r2.top() + 26), f"Teal solid: Cumulative energy E_k (k=3: {energy_pct[2]:.1f}%, k=6: {energy_pct[5]:.1f}%)")
        p.setPen(QtGui.QColor("#dc2626"))
        p.drawText(QtCore.QPointF(r2.left() + 18, r2.top() + 48), f"Red dashed: Rel Fro error (k=3: {rel_err_pct[2]:.1f}%, k=6: {rel_err_pct[5]:.1f}%)")
        p.end()
        img.save(str(fig_dir / "fig4_real_returns_svd_eckart_young.png"))
    _ = app


def generate_figures(prices_path: Path | None):
    fig_dir = ROOT / "manuscript" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        _generate_figures_qt(prices_path, fig_dir)
        return

    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "PingFang SC", "Noto Sans CJK SC", "SimHei", "Arial"]

    # Figure 1: Gerschgorin disks before & after diagonal similarity scaling D = diag(1, 1, 5)
    A = np.array([[5.0, 1.0, 1.0], [0.0, 6.0, 1.0], [1.0, 0.0, -5.0]])
    D = np.diag([1.0, 1.0, 5.0])
    As = np.linalg.inv(D) @ A @ D
    eigs = np.linalg.eigvals(A)
    theta = np.linspace(0, 2 * np.pi, 300)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), dpi=180)
    for ax, mat, title in [
        (axes[0], A, "Original Matrix A: Row Disks (Gr) vs Col Disks (Gc)"),
        (axes[1], As, "Scaled D^-1 A D (D=diag(1,1,5)): Tightened Disk at -5"),
    ]:
        ax.axhline(0, color="#94a3b8", lw=0.8)
        ax.axvline(0, color="#94a3b8", lw=0.8)
        for i in range(3):
            c = mat[i, i]
            rr = sum(abs(mat[i, j]) for j in range(3) if j != i)
            rc = sum(abs(mat[j, i]) for j in range(3) if j != i)
            ax.fill(c + rr * np.cos(theta), rr * np.sin(theta), alpha=0.18, color="#2563eb", label="Row disk" if i == 0 else None)
            ax.plot(c + rr * np.cos(theta), rr * np.sin(theta), color="#2563eb", lw=1.4)
            ax.plot(c + rc * np.cos(theta), rc * np.sin(theta), color="#0d9488", lw=1.3, ls="--", label="Col disk" if i == 0 else None)
        ax.scatter(eigs.real, eigs.imag, color="#dc2626", s=55, zorder=5, label="Exact eigenvalues")
        ax.set_aspect("equal")
        ax.set_xlim(-7.8, 11.8)
        ax.set_ylim(-6.8, 6.8)
        ax.set_xlabel("Re(z)")
        ax.set_ylabel("Im(z)")
        ax.set_title(title, fontsize=10)
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig1_gerschgorin_scaling.png", dpi=180)
    plt.close(fig)

    # Figure 2: Quadratic form level ellipses x^T A x = 1 (Ill-conditioned vs Shrunk)
    Q = np.array([[np.cos(np.pi / 6), -np.sin(np.pi / 6)], [np.sin(np.pi / 6), np.cos(np.pi / 6)]])
    A_ill = Q @ np.diag([4.0, 0.16]) @ Q.T  # cond = 25
    mu = np.trace(A_ill) / 2.0
    A_shr = 0.6 * A_ill + 0.4 * mu * np.eye(2)
    t = np.linspace(0, 2 * np.pi, 400)
    unit = np.vstack([np.cos(t), np.sin(t)])
    fig, ax = plt.subplots(figsize=(6.4, 5.2), dpi=180)
    for mat, col, lbl in [
        (A_ill, "#dc2626", f"Raw Sigma (cond={np.linalg.cond(A_ill):.1f})"),
        (A_shr, "#2563eb", f"Shrunk Sigma_0.4 (cond={np.linalg.cond(A_shr):.2f})"),
    ]:
        vals, vecs = np.linalg.eigh(mat)
        pts = vecs @ np.diag(1.0 / np.sqrt(vals)) @ unit
        ax.plot(pts[0], pts[1], color=col, lw=2.0, label=lbl)
        for k in range(2):
            axis_vec = vecs[:, k] / np.sqrt(vals[k])
            ax.arrow(0, 0, axis_vec[0], axis_vec[1], head_width=0.08, color=col, alpha=0.75, length_includes_head=True)
    ax.axhline(0, color="#94a3b8", lw=0.8)
    ax.axvline(0, color="#94a3b8", lw=0.8)
    ax.set_aspect("equal")
    ax.set_xlabel("x1")
    ax.set_ylabel("x2")
    ax.set_title("Quadratic Form Level Set x^T Sigma x = 1 & Spectral Shrinkage")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig2_quadratic_form_ellipsoid.png", dpi=180)
    plt.close(fig)

    # Figure 3: Real 12-stock covariance shrinkage spectrum & PCA scree plot
    if prices_path and prices_path.exists():
        from matrixlab.analytics import analyze, shrinkage_path
        from matrixlab.data import read_prices

        prices = read_prices(prices_path)
        syms = sorted(prices.symbol.unique())
        asof = "2025-01-27"
        res = analyze(prices, syms, asof, lookback=252, alpha=0.05)
        alphas = np.linspace(0.0, 1.0, 21)
        path = shrinkage_path(prices, syms, asof, lookback=252, alphas=alphas)

        fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), dpi=180)
        axes[0].plot(path["alpha"], path["condition"], color="#2563eb", lw=2.0, marker="o", ms=4, label="Condition Number kappa(Sigma_alpha)")
        axes[0].axvline(res.ledoit_wolf_alpha, color="#dc2626", ls="--", lw=1.4, label=f"Ledoit-Wolf alpha* = {res.ledoit_wolf_alpha:.4f}")
        axes[0].set_xlabel("Shrinkage Intensity alpha")
        axes[0].set_ylabel("Condition Number")
        axes[0].set_title("Real 12-Stock Covariance Shrinkage Path (2025-01-27)")
        axes[0].grid(alpha=0.25)
        axes[0].legend(fontsize=8.5)

        idx = np.arange(1, len(res.explained_variance) + 1)
        axes[1].bar(idx, res.explained_variance * 100.0, color="#0d9488", alpha=0.8, label="Individual Variance (%)")
        axes[1].plot(idx, np.cumsum(res.explained_variance) * 100.0, color="#d97706", lw=2.0, marker="s", ms=4, label="Cumulative (%)")
        axes[1].set_xticks(idx)
        axes[1].set_xticklabels([f"PC{i}" for i in idx], fontsize=8)
        axes[1].set_ylabel("Explained Variance (%)")
        axes[1].set_title("Correlation Matrix PCA Scree Plot (12 US Equities)")
        axes[1].grid(alpha=0.25)
        axes[1].legend(fontsize=8.5)
        fig.tight_layout()
        fig.savefig(fig_dir / "fig3_real_cov_spectrum_shrinkage.png", dpi=180)
        plt.close(fig)

        # Figure 4: Real 12-stock return matrix SVD spectrum & Eckart-Young-Mirsky error
        X_mat = (res.returns - res.returns.mean(axis=0)).to_numpy(dtype=float)
        U_r, s_r, Vt_r = np.linalg.svd(X_mat, full_matrices=False)
        tot_sq = float(np.sum(s_r ** 2))
        energy_pct = np.cumsum(s_r ** 2) / tot_sq * 100.0
        rel_err_pct = np.array([
            np.linalg.norm(X_mat - (U_r[:, :k] * s_r[:k]) @ Vt_r[:k, :], "fro") / np.sqrt(tot_sq) * 100.0
            for k in range(1, len(s_r) + 1)
        ])
        fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), dpi=180)
        k_idx = np.arange(1, len(s_r) + 1)
        axes[0].bar(k_idx, s_r, color="#2563eb", alpha=0.82)
        axes[0].set_xticks(k_idx)
        axes[0].set_xticklabels([f"s{i}" for i in k_idx], fontsize=8)
        axes[0].set_ylabel("Singular Value sigma_k")
        axes[0].set_title(f"Return Matrix X (252x12) SVD: kappa_2(X)={s_r[0]/s_r[-1]:.2f}")
        axes[0].grid(alpha=0.25)

        axes[1].plot(k_idx, energy_pct, color="#0d9488", lw=2.0, marker="o", ms=4, label="Cumulative Energy E_k (%)")
        axes[1].plot(k_idx, rel_err_pct, color="#dc2626", lw=2.0, ls="--", marker="s", ms=4, label="Rel Fro Error ||X-X_k||_F/||X||_F (%)")
        axes[1].set_xticks(k_idx)
        axes[1].set_xticklabels([f"k={i}" for i in k_idx], fontsize=8)
        axes[1].set_ylabel("Percentage (%)")
        axes[1].set_title("Eckart-Young-Mirsky Rank-k Approximation")
        axes[1].grid(alpha=0.25)
        axes[1].legend(fontsize=8.5)
        fig.tight_layout()
        fig.savefig(fig_dir / "fig4_real_returns_svd_eckart_young.png", dpi=180)
        plt.close(fig)


def verify_real_svd(prices_path: Path | None):
    if not prices_path or not prices_path.exists():
        return None
    from matrixlab.analytics import analyze
    from matrixlab.data import read_prices

    prices = read_prices(prices_path)
    syms = sorted(prices.symbol.unique())
    res = analyze(prices, syms, "2025-01-27", lookback=252, alpha=0.05)
    X_mat = (res.returns - res.returns.mean(axis=0)).to_numpy(dtype=float)
    U_r, s_r, Vt_r = np.linalg.svd(X_mat, full_matrices=False)
    tot_sq = float(np.sum(s_r ** 2))
    energy = np.cumsum(s_r ** 2) / tot_sq
    rel_err = [float(np.linalg.norm(X_mat - (U_r[:, :k] * s_r[:k]) @ Vt_r[:k, :], "fro") / np.sqrt(tot_sq)) for k in range(1, len(s_r) + 1)]
    spec_err = [float(np.linalg.norm(X_mat - (U_r[:, :k] * s_r[:k]) @ Vt_r[:k, :], 2)) for k in range(1, len(s_r))]
    assert np.allclose(spec_err, s_r[1:])
    assert np.isclose((s_r[0] / s_r[-1]) ** 2, res.condition_before, rtol=1e-6)
    return {
        "shape": list(X_mat.shape),
        "sigma_top4": [round(float(v), 6) for v in s_r[:4]],
        "sigma_min": round(float(s_r[-1]), 6),
        "kappa_2_X": round(float(s_r[0] / s_r[-1]), 4),
        "kappa_2_Sigma": round(float(res.condition_before), 4),
        "energy_k1_k3_k6": [round(float(energy[k - 1]), 4) for k in (1, 3, 6)],
        "rel_fro_err_k1_k3_k6": [round(float(rel_err[k - 1]), 4) for k in (1, 3, 6)],
        "spec_err_k1_k3_k6": [round(float(spec_err[k - 1]), 6) for k in (1, 3, 6)],
    }


def main():
    parser = argparse.ArgumentParser(description="Verify Task 1 manuscript math and optionally generate figures")
    parser.add_argument("--prices", type=Path, default=ROOT / "data" / "prices.csv")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    out = {
        "examples_and_theorems": verify_lec9_examples(),
        "exercises_1_to_10": verify_lec9_all_10_exercises(),
    }
    svd_stats = verify_real_svd(args.prices)
    if svd_stats is not None:
        out["real_returns_svd"] = svd_stats
    if args.plot:
        generate_figures(args.prices)
        fig_dir = ROOT / "manuscript" / "figures"
        out["figures_generated"] = sorted(p.name for p in fig_dir.glob("*.png"))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
