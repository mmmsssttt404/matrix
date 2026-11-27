# 第五/六章联动精修专题：矩阵范数、条件数与奇异值分解（SVD）

> **对应课程范围**：第五章（`Lec6.pdf` p.10–16，Meyer §5.1–5.2）与第六章（`Lec7.pdf` p.50–57，Meyer §5.12）。本专题与主修章[第八章修订稿](chapter8_eigenvalues_and_psd_revised.md)及题目二量化组合风控形成完整理论闭环。

---

## 一、诱导矩阵范数、次可乘性与谱范数推导（对应 `Lec6` p.10–16）

### 1.1 为什么矩阵范数必须满足次可乘性？

`Lec6` p.11 指出，方阵空间 $\mathbb{C}^{n\times n}$（以及维度相容的矩形矩阵乘法族）不仅是向量空间，还具有乘法代数结构，因此一般矩阵范数除正定性、齐次性与三角不等式外，还要求**次可乘性（submultiplicativity）**：$\|AB\| \le \|A\|\|B\|$。

> **【增补-推导】诱导矩阵范数必然满足相容性与次可乘性**  
> 设 $\|\cdot\|_v$ 为任意向量范数，定义诱导（算子）矩阵范数：
> $$\|A\| = \max_{\|x\|_v = 1} \|Ax\|_v = \max_{x\neq 0} \frac{\|Ax\|_v}{\|x\|_v}.$$
> - **与向量范数相容**：对非零 $x$，$\|Ax\|_v = \|x\|_v \cdot \|A(x/\|x\|_v)\|_v \le \|A\|\|x\|_v$（$x=0$ 平凡成立）。  
> - **次可乘性**：对任意 $\|x\|_v = 1$，$\|(AB)x\|_v = \|A(Bx)\|_v \le \|A\|\|Bx\|_v \le \|A\|\|B\|\|x\|_v = \|A\|\|B\|$，对所有单位向量取极大即得 $\|AB\| \le \|A\|\|B\|$。$\blacksquare$  
> - **谱范数 $\|A\|_2 = \sqrt{\lambda_{\max}(A^*A)} = \sigma_1(A)$**：因为 $A^*A$ 是 Hermite 半正定阵，由第八章 **Rayleigh–Ritz 定理**（定理 8.4）：
>   $$\|A\|_2^2 = \max_{\|x\|_2=1} \|Ax\|_2^2 = \max_{\|x\|_2=1} \frac{x^*(A^*A)x}{x^*x} = \lambda_{\max}(A^*A) = \sigma_1(A)^2.$$
>   同理，若 $A$ 非奇异，则 $\min_{\|x\|_2=1}\|Ax\|_2 = \sqrt{\lambda_{\min}(A^*A)} = \sigma_n(A) = 1/\|A^{-1}\|_2$，这就将 `Lec6` p.13–14 的范数公式与第八章的 Rayleigh 商彻底打通。参考：Meyer §5.2 (p.279–282)；Horn & Johnson (2013) §5.6。

---

## 二、条件数与线性系统扰动界（对应 `Lec7` p.52–54）

设非奇异系统 $Ax = b$（$b\neq 0$，故 $x\neq 0$）存在右端扰动 $A(x+\Delta x) = b + \Delta b$（即 $A\Delta x = \Delta b$）。由相容性得 $\|\Delta x\| = \|A^{-1}\Delta b\| \le \|A^{-1}\|\|\Delta b\|$ 与 $\|b\| = \|Ax\| \le \|A\|\|x\|$，两式相乘即得相对误差放大上界：

$$\frac{\|\Delta x\|}{\|x\|} \le \|A\|\|A^{-1}\| \cdot \frac{\|\Delta b\|}{\|b\|} = \kappa(A)\frac{\|\Delta b\|}{\|b\|}.$$

> **【增补-知识关联（联动题目二组合权重稳定性）】**  
> 在题目二的无约束最小方差闭式解 $w^* = \frac{\Sigma^{-1}\mathbf{1}}{\mathbf{1}^T \Sigma^{-1}\mathbf{1}}$ 中，求解核心就是线性方程组 $\Sigma z = \mathbf{1}$！当资产收益率高度相关或样本量 $T$ 相对资产数 $N$ 偏小时，样本协方差 $\Sigma$ 的 2-条件数 $\kappa_2(\Sigma) = \sigma_1/\sigma_n = \lambda_{\max}/\lambda_{\min}$ 会急剧膨胀（如 12 只美股上 $\kappa_2(\Sigma)=48.30$），导致极小的协方差估计误差被剧烈放大为极端权重与高换手率。这正是 Ledoit–Wolf 谱收缩 $\Sigma_\alpha = (1-\alpha)\Sigma + \alpha\mu I$ 将条件数从 `48.30` 压低至 `30.78`、并同步降低样本外换手率的根本线性代数机制。

---

## 三、SVD、Eckart–Young–Mirsky 最佳低秩逼近与现代大模型应用（对应 `Lec7` p.50–57 & `Lec0`）

设 $A \in \mathbb{C}^{m\times n}$ 秩为 $r$，奇异值分解为 $A = U \Sigma V^* = \sum_{i=1}^r \sigma_i u_i v_i^*$（$\sigma_1 \ge \cdots \ge \sigma_r > 0$）。对任意 $1 \le k < r$，定义截断 SVD 矩阵 $A_k = \sum_{i=1}^k \sigma_i u_i v_i^*$。

> **【增补-推导】补全 `Lec7` p.55–56 省略的 Eckart–Young–Mirsky 定理（2-范数与 Frobenius 范数）严格证明**  
> **定理（Eckart–Young–Mirsky，1936/1960）**：对一切满足 $\mathrm{rank}(B)\le k$ 的矩阵 $B\in\mathbb{C}^{m\times n}$，恒有：
> $$\|A - B\|_2 \ge \|A - A_k\|_2 = \sigma_{k+1}, \qquad \|A - B\|_F \ge \|A - A_k\|_F = \sqrt{\sum_{i=k+1}^r \sigma_i^2}.$$
> **2-范数证明**：首先 $A - A_k = \sum_{i=k+1}^r \sigma_i u_i v_i^*$ 的最大奇异值为 $\sigma_{k+1}$，故 $\|A - A_k\|_2 = \sigma_{k+1}$。下证任意 $\mathrm{rank}(B)\le k$ 均有 $\|A-B\|_2\ge \sigma_{k+1}$：由秩-零化度定理，$\dim N(B) = n - \mathrm{rank}(B) \ge n - k$；令 $\mathcal{V}_{k+1} = \mathrm{span}\{v_1,\dots,v_{k+1}\}$（维数 $k+1$）。因为 $\dim N(B) + \dim \mathcal{V}_{k+1} \ge n + 1 > n$，故必存在单位向量 $x \in N(B)\cap \mathcal{V}_{k+1}$。写 $x = \sum_{i=1}^{k+1} c_i v_i$（$\sum |c_i|^2 = 1$），则 $Bx = 0$ 且：
> $$\|A - B\|_2^2 \ge \|(A-B)x\|_2^2 = \|Ax\|_2^2 = \left\|\sum_{i=1}^{k+1} \sigma_i c_i u_i\right\|_2^2 = \sum_{i=1}^{k+1} \sigma_i^2 |c_i|^2 \ge \sigma_{k+1}^2 \sum_{i=1}^{k+1}|c_i|^2 = \sigma_{k+1}^2. \quad \blacksquare$$
> **Frobenius 范数自洽证明（直接由 2-范数结论推得）**：对每个 $i=1,\dots,r-k$，令 $(A-B)_{i-1}$ 为 $A-B$ 的秩 $(i-1)$ 截断 SVD，则 $\mathrm{rank}\big(B + (A-B)_{i-1}\big) \le k + i - 1$。直接应用已证的 2-范数最佳低秩界即得：
> $$\sigma_i(A-B) = \|(A-B)-(A-B)_{i-1}\|_2 = \big\|A - \big(B+(A-B)_{i-1}\big)\big\|_2 \ge \sigma_{k+i}(A).$$
> 将上式平方求和即得 $\|A-B\|_F^2 = \sum_{i=1}^{\min(m,n)} \sigma_i(A-B)^2 \ge \sum_{i=1}^{r-k}\sigma_{k+i}(A)^2 = \sum_{t=k+1}^r \sigma_t^2 = \|A-A_k\|_F^2$。$\blacksquare$  
> 参考：Golub & Van Loan (2013) Theorem 2.4.8；Strang (2019) §I.8–I.9；Meyer §5.12 (p.417–418，2-范数情形)；Goodfellow et al. (2016) §2.8。

> **【增补-现代应用】SVD 低秩逼近在图像压缩、推荐系统与大语言模型中的统一视角（衔接 `Lec0` p.12, p.16, p.24）**
> 1. **图像压缩（`Lec0` p.12）**：$500\times 500$ 灰度图像矩阵取前 $k$ 阶截断 SVD，存储量由 $mn$ 降至 $k(m+n+1)$，压缩比 $5\text{–}12.5\times$ 时因奇异值快速衰减仍能保持清晰轮廓；
> 2. **推荐系统矩阵分解（`Lec0` p.16）**：评分矩阵 $R \approx P Q^T$ 本质是带观测缺失与 $L_2$ 正则化的低秩分解；
> 3. **大语言模型微调（LoRA）与推理压缩（DeepSeek-V3 MLA，`Lec0` p.24）**：LoRA 将权重更新量参数化为低秩矩阵 $\Delta W = B A$（秩 $r \ll \min(d_{\text{in}}, d_{\text{out}})$）；DeepSeek-V3 的多头潜在注意力（MLA）将高维 Key-Value 矩阵联合低秩投影到紧凑潜向量 $c_t^{KV}$ 缓存，再在推理时升维恢复，本质上都是利用权重/特征矩阵的近似低秩结构换取数量级的显存与带宽节省。
