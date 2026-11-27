# 题目一修改说明、原课件勘误与参考文献核验表

> 本文件对应大作业要求第 3 节（4）–（5）：“标明关键改动和对应参考来源；提交：修订稿 + 修改说明”。

## 1. 选定章节与整体修订思路

- **主修章节**：**第八章《特征值、特征向量与正定矩阵》**（严格对应课程 `Lec9.pdf` 与主教材 Carl D. Meyer *Matrix Analysis and Applied Linear Algebra* 第 7 章 `7.1`, `7.2`, `7.5`, `7.6` 节），交付稿件：[chapter8_eigenvalues_and_psd_revised.md](chapter8_eigenvalues_and_psd_revised.md)。
- **联动精修专题**：**第五/六章核心节《矩阵范数、条件数与奇异值分解（SVD）》**（对应 `Lec6.pdf` p.10–16、`Lec7.pdf` p.50–57 与 Meyer 第 5 章 `5.1`, `5.2`, `5.12` 节），交付稿件：[chapter5_6_norms_svd_supplement.md](chapter5_6_norms_svd_supplement.md)。
- **修订核心原则**：
  1. **修复原课件中的遗漏定理与印刷/表述错误**（共核查并修正 `Lec9` 中 **8 页共 10 处**具体问题，见第 2 节）；
  2. **补齐跳步证明**（补全 $\rho(A)\le\|A\|$、Gerschgorin 圆盘、Schur 酉三角化、$g_A(\lambda)\le a_A(\lambda)$、Lagrange 谱投影、正规矩阵酉对角化、Rayleigh–Ritz、Courant–Fischer、Weyl 扰动、Sylvester 惯性定律、Eckart–Young–Mirsky 共 11 项关键证明）；
  3. **强化几何直观与现代应用联动**（绘制 3 张可复现高清配图，并将正定矩阵、谱收缩、条件数、PCA 直接接入本项目题目二 12 只美股真实数据，同时呼应 `Lec0` 中的 PageRank、图像压缩、DeepSeek-V3 MLA 低秩压缩）；
  4. **全部算例与课后 10 题机器验算**：编写独立验算脚本 [verify_manuscript_math.py](verify_manuscript_math.py) 对全部例题、反例、定理性质与 `Lec9` p.31–32 全部 10 道课后题（5 道计算题精确校验 + 5 道证明题随机数值性质检验）完成校验。

---

## 2. 关键改动与原课件勘误逐条对照表

| 编号 | 所在章节与原课件/教材位置 | 原稿痛点、遗漏或勘误 | 本次关键修改内容 | 对应参考来源与核验方式 |
|---|---|---|---|---|
| **M1** | §8.1.1–8.1.2 (`Lec9` p.2–6; Meyer §7.1 p.489–493) | 仅给出 $u'=Au$ 计算步骤与“五次以上方程无根式解”口头陈述，缺少解耦物理直觉、复特征值旋转几何含义及实用迭代算法衔接 | 增补系统解耦解释、复特征值 $re^{\pm i\theta}$ 旋转缩放几何解释、伴随矩阵与 Abel–Ruffini 等价性、Wilkinson 多项式数值灾难案例，引出 Hessenberg + Francis QR 迭代 | Meyer §7.1 (p.489–493); Golub & Van Loan (2013) §7.3–7.5; Strang (2019) §I.6 |
| **M2** | §8.1.3 (`Lec9` p.7, p.10–11; Meyer p.497–499) | **勘误**：p.7 印错 `"principal minor if the determinant"`（应为 `is`）；p.10 跳过 $\rho(A)\le\|A\|$ 证明且未强调次可乘性前提；p.11 Gerschgorin 例题无精确值核对与缩放技巧 | 补全 $\rho(A)\le\|A\|$ 与 Gerschgorin 圆盘完整证明、补充非次可乘反例与 Gelfand 公式；对 p.11 矩阵做对角相似缩放 $D=\mathrm{diag}(1,1,5)$ 将 $-5$ 处圆盘半径由 `1.0` 收紧至 `0.2`（并结合实阵共轭对推出必为实根），绘制 **图 8.1** 标出精确特征值 `{-5.090, 5.000, 6.090}` | Meyer §7.1 (p.497–499); Horn & Johnson (2013) Thm. 5.6.9, Thm. 5.6.12, Cor. 5.6.14, Cor. 6.1.6; `verify_manuscript_math.py` |
| **M3** | §8.2.1 (`Lec9` p.12, p.15–21; Meyer §7.2 p.505–518) | **勘误**：p.12 出现重复短语 `"or the analysis of a particular problem"` 两遍；p.15 拼写错 `"diagonlizable"`、`"in variant"`；Schur 定理、重数不等式与 Lagrange 谱投影公式均无证明 | 补全 Schur 酉三角化归纳证明（显式衔接 `Lec6` Householder 酉基扩充并分析 $\kappa_2(U)=1$ 的数值优势）、补全 $g_A(\lambda)\le a_A(\lambda)$ 分块证明与谱投影 $G_i=\ell_i(A)$ 推导，补充亏损矩阵向 Jordan 形的过渡 | Meyer §7.2–7.3 (p.508–529); Horn & Johnson (2013) Thm. 2.3.1; `verify_manuscript_math.py` |
| **M4** | §8.3.1 (`Lec9` p.22–23, p.32 Ex.9; Meyer §7.5 p.547–549) | **勘误**：p.22 拼写错 `"egenvector"`、`"and is such a complete set"`；p.32 Ex.9 拼写错 `"it ie diagonal"`；正规矩阵酉对角化只给结论未给证明 | 补全“利用 Schur 定理 + 上三角正规阵必为对角阵”的极简充要证明，直接贯通 `Lec9` 习题 9 | Meyer §7.5 (p.547–549); Horn & Johnson (2013) Thm. 2.5.3 |
| **M5** | **§8.3.2 (`Lec9` p.24; Meyer §7.5 p.550–553)** | **重大遗漏（高价值发现）**：`Lec9` 第 24 页列出 *"Largest and Smallest Eigenvalues"* 与 *"Eigenvalue Perturbations"* 两个小标题，却**遗漏了公式主体**（仅保留前提设定句） | 完整补齐并严格证明 **Rayleigh–Ritz 变分定理**、**Courant–Fischer 极小极大定理**与 **Weyl 特征值扰动不等式** $\lambda_i+\epsilon_n \le \beta_i \le \lambda_i+\epsilon_1$（及次可乘范数界），对比说明为何对称阵特征值良态而亏损阵敏感，并补全 Cauchy 交错证明 | Meyer §7.5 (p.550–553); Horn & Johnson (2013) Thm. 4.2.2, 4.2.6, 4.3.1; `verify_manuscript_math.py` |
| **M6** | **§8.4.1–8.4.2 (`Lec9` p.26–30; Meyer §7.6 p.558–570)** | **勘误与精确化**：p.28 拼写错 `"factorzation"` 且断言 *"When A has zero eigenvalues, there is no LU factorzation"* 不够严密；未说明为何半正定需检查全部 $2^n-1$ 个主子式；p.30 跳过 **Sylvester 惯性定律** | 构造精确反例 $\mathrm{diag}(0,-1)$ 与 $\mathrm{diag}(1,0)$，严格区分精确算术下奇异 PSD 阵**存在但不唯一/非正对角**的 $LDL^T$/$R^TR$ 分解与浮点下需完全对称主元选择的工程原因（经多 Agent 数学审查二次修正！）；绘制二次型等值椭球 **图 8.2**；补全 **Sylvester 惯性定律**证明 | Meyer §7.6 (p.558–570); Horn & Johnson (2013) Cor. 7.2.9, Thm. 4.5.8; Golub & Van Loan (2013) §4.2.8–4.2.9 |
| **M7** | §8.4.3（双题联动新增实战案例） | 原教材案例偏经典物理（弹簧/弦振动，Meyer p.560），缺乏与当代金融数据及 AI 系统的实战衔接 | 新增定理 8.10（线性谱收缩特征值平移与条件数严格单调下降证明），接入题目二真实 12 只美股数据（`2025-01-27`, $T=252$）实证展示 $\kappa(\Sigma): 48.30 \to 30.78$（Ledoit-Wolf $\alpha^*=0.0635$）、PCA 碎石图（**图 8.3**）与样本外滚动夏普提升（`1.64 → 2.26`） | Ledoit & Wolf (2004, JMVA); 本项目 `data/prices.csv` & `matrixlab/analytics.py` |
| **M8** | §8.5.2 (`Lec9` p.31–32 习题 1–10) | 原课件只留习题无解答，且 p.31 习题 4 误将分块矩阵右上块印为 `mb`（应为 `B`） | 纠正印刷错误，逐题给出全部 10 道习题的严谨手推步骤，并经 `verify_manuscript_math.py` 自动化数值校验（特别是习题 8 正规性验证与习题 10 矩阵 $B$ 奇异半正定辨析） | Meyer §7.1–7.6 习题与 *Solutions Manual*; `verify_manuscript_math.py` |
| **M9** | 联动专题（`Lec6` p.10–16, `Lec7` p.50–57; Meyer §5.2, §5.12） | `Lec6` 未完整证明诱导范数次可乘性与 $\|A\|_2=\sigma_1$ 经由 Rayleigh 商的联系；`Lec7` 省略了 Eckart–Young–Mirsky 最佳低秩逼近证明 | 补全诱导范数相容/次可乘证明、线性系统条件数扰动界与组合权重稳定性联系、Eckart–Young–Mirsky 2-范数与自洽 Frobenius 范数证明，并统一解释 `Lec0` 中的图像压缩、推荐系统与 DeepSeek-V3 MLA / LoRA 低秩压缩 | Meyer §5.2 (p.279–282), §5.12 (p.417–418); Golub & Van Loan (2013) Thm. 2.4.8; Strang (2019) §I.8–I.9; Goodfellow et al. (2016) §2.8 |

---

## 3. 权威参考文献核验清单

下表所列参考文献均与课程 `Lec0.pdf` 第 7 页推荐书单及已核实原始 PDF / 论文记录严格对齐，无任何虚构文献或幻觉定理号：

1. **Carl D. Meyer (2000)**. *Matrix Analysis and Applied Linear Algebra* (and accompanying *Solutions Manual*). Society for Industrial and Applied Mathematics (SIAM), Philadelphia.  
   - *核验方式*：直接核对课程归档原书 PDF（§5.1–5.2 p.269–285；§5.12 p.411–428；§7.1 p.489–504；§7.2 p.505–524；§7.5 p.547–557；§7.6 p.558–573）。
2. **Roger A. Horn & Charles R. Johnson (2013)**. *Matrix Analysis* (2nd Edition). Cambridge University Press.  
   - *引用条目*：Theorem 2.3.1 (Schur), Theorem 2.5.3 (Normal matrices), Theorems 4.2.2 / 4.2.6 / 4.3.1 (Rayleigh–Ritz, Courant–Fischer, Weyl), Theorem 4.5.8 (Sylvester's Law of Inertia), Theorems 5.6.9 & 5.6.12 & Corollary 5.6.14 (Spectral radius & Gelfand), Corollary 6.1.6 (Gerschgorin scaling), Corollary 7.2.9 (PSD/Cholesky).
3. **Gilbert Strang (2019)**. *Linear Algebra and Learning from Data*. Wellesley-Cambridge Press.  
   - *引用条目*：§I.6 (Eigenvalues and Eigenvectors), §I.7 (Symmetric Positive Definite Matrices), §I.8 (Singular Values and Singular Vectors in the SVD), §I.9 (Principal Components and the Best Low Rank Matrix / Eckart–Young).
4. **Gene H. Golub & Charles F. Van Loan (2013)**. *Matrix Computations* (4th Edition). Johns Hopkins University Press.  
   - *引用条目*：Theorem 2.4.8 (Eckart–Young–Mirsky), §4.2.8–4.2.9 (Pivoted Cholesky for PSD), §7.3–7.5 (Hessenberg reduction & QR algorithm).
5. **Ian Goodfellow, Yoshua Bengio & Aaron Courville (2016)**. *Deep Learning*. MIT Press.  
   - *引用条目*：Chapter 2 (§2.7–2.12 Eigendecomposition, SVD, PCA).
6. **Olivier Ledoit & Michael Wolf (2004)**. "A well-conditioned estimator for large-dimensional covariance matrices." *Journal of Multivariate Analysis*, 88(2), 365–411.
7. **中国科学院大学《矩阵分析与应用》课程原始课件**：`Lec0.pdf`（孙翼）、`lec6.pdf`、`lec7.pdf`、`lec9.pdf`（李保滨）。
