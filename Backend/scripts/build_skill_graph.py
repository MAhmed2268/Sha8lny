"""
build_skill_graph.py
====================
Normalization pipeline.

Sources (all read-only):
  Backend/data/raw/esco_occupations.csv          → ESCO occupations
  Backend/data/raw/esco_occupation_skills.csv    → ESCO occupation-skill relations
  Backend/data/raw/onet_skills.csv               → O*NET cognitive/foundational skills (IM scale 1-5)
  Backend/data/raw/onet_tech_skills.csv          → O*NET technology skills (Hot/InDemand flags)

Output:
  Backend/data/role_graph.json

Level mapping (O*NET Importance, 1-5 scale):
  score <  2.50  →  beginner
  score <  3.75  →  intermediate
  score >= 3.75  →  advanced

Importance filter threshold: 2.5 (skills below this are dropped)

O*NET Tech-skill importance derivation:
  Hot=Y, InDemand=Y  →  4.5  (advanced)
  Hot=Y, InDemand=N  →  3.0  (intermediate)
  Hot=N, InDemand=Y  →  3.5  (intermediate)
  Hot=N, InDemand=N  →  1.5  (dropped — below threshold)
"""

import json
import os
import re
import sys

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────

_HERE     = os.path.dirname(os.path.abspath(__file__))
BASE_DIR  = os.path.dirname(_HERE)
RAW_DIR   = os.path.join(BASE_DIR, "data", "raw")
OUT_PATH  = os.path.join(BASE_DIR, "data", "role_graph.json")

# ── Constants ─────────────────────────────────────────────────────────────

IMPORTANCE_THRESHOLD = 2.5

VALID_LEVELS = {"beginner", "intermediate", "advanced"}

TECH_FLAG_SCORE = {
    ("Y", "Y"): 4.5,
    ("Y", "N"): 3.0,
    ("N", "Y"): 3.5,
    ("N", "N"): 1.5,
}

ESCO_ESSENTIAL_SCORE = 3.5
ESCO_OPTIONAL_SCORE  = 2.5

TARGET_ROLES = [
    (
        "software_developer",
        "software developer",
        ["15-1251.00"],
        ["15-1252.00", "15-1251.00"],
    ),
    (
        "frontend_developer",
        "web developer",
        ["15-1254.00"],
        ["15-1254.00", "15-1255.00"],
    ),
    (
        "data_scientist",
        "data scientist",
        ["15-2051.01", "15-2041.00", "15-2041.01"],
        ["15-2051.01", "15-2041.00"],
    ),
    (
        "backend_engineer",
        "software developer",
        ["15-1299.08", "15-1211.00"],
        ["15-1299.08", "15-1251.00"],
    ),
    (
        "machine_learning_engineer",
        "artificial intelligence engineer",
        ["15-1221.00", "15-2051.01"],
        ["15-1221.00", "15-2051.01"],
    ),
    (
        "devops_engineer",
        "cloud DevOps engineer",
        ["15-1299.08", "15-1244.00", "15-1241.00"],
        ["15-1299.08", "15-1244.00", "15-1241.00"],
    ),
]

# ── Skill-name aliases ─────────────────────────────────────────────────────

_RAW_ALIASES = [
    (r"\breact\.?js\b",                          "React"),
    (r"\bvue\.?js\b",                            "Vue.js"),
    (r"\bangular\.?js\b",                        "Angular"),
    (r"\bnode\.?js\b",                           "Node.js"),
    (r"\bnext\.?js\b",                           "Next.js"),
    (r"\bexpress\.?js\b",                        "Express.js"),
    (r"\bjavascript\b",                          "JavaScript"),
    (r"\btypescript\b",                          "TypeScript"),
    (r"\bpython\s*(\(computer\s*programming\))?", "Python"),
    (r"\bjava\s*(\(computer\s*programming\))?",   "Java"),
    (r"\bc#\b",                                  "C#"),
    (r"\bc\+\+\b",                               "C++"),
    (r"\bgo\s*(\(programming\))?\b",             "Go"),
    (r"\brust\b",                                "Rust"),
    (r"\bscala\b",                               "Scala"),
    (r"\bkotlin\b",                              "Kotlin"),
    (r"\bswift\s*(\(computer\s*programming\))?", "Swift"),
    (r"\bruby\s*(\(computer\s*programming\))?",  "Ruby"),
    (r"\bphp\b",                                 "PHP"),
    (r"\bcobol\b",                               "COBOL"),
    (r"\bmatlab\b",                              "MATLAB"),
    (r"\br\b(?!\w)",                             "R"),
    (r"\bsql\b",                                 "SQL"),
    (r"\bnosql\b",                               "NoSQL"),
    (r"\bpostgresql\b",                          "PostgreSQL"),
    (r"\bmysql\b",                               "MySQL"),
    (r"\bmongodb\b",                             "MongoDB"),
    (r"\bredis\b",                               "Redis"),
    (r"\belasticsearch\b",                       "Elasticsearch"),
    (r"\bcassandra\b",                           "Apache Cassandra"),
    (r"\bapache\s*cassandra\b",                  "Apache Cassandra"),
    (r"\bamazon\s*web\s*services\s*aws\s*software\b", "AWS"),
    (r"\bamazon\s*web\s*services\b",             "AWS"),
    (r"\baws\b(?!\s*cloudformation)",            "AWS"),
    (r"\baws\s*cloudformation\b",                "AWS CloudFormation"),
    (r"\bmicrosoft\s*azure\b",                   "Azure"),
    (r"\bgoogle\s*cloud\b",                      "Google Cloud"),
    (r"\bgcp\b",                                 "Google Cloud"),
    (r"\bdocker\b",                              "Docker"),
    (r"\bkubernetes\b",                          "Kubernetes"),
    (r"\bterraform\b",                           "Terraform"),
    (r"\bansible\s*(software)?\b",               "Ansible"),
    (r"\bjenkins\b",                             "Jenkins"),
    (r"\bgitlab\b",                              "GitLab"),
    (r"\bgithub\b",                              "GitHub"),
    (r"\bgit\b",                                 "Git"),
    (r"\bci/cd\b",                               "CI/CD"),
    (r"\bbash\b",                                "Bash"),
    (r"\blinux\b",                               "Linux"),
    (r"\btensorflow\b",                          "TensorFlow"),
    (r"\bpytorch\b",                             "PyTorch"),
    (r"\bscikit[-\s]?learn\b",                   "Scikit-learn"),
    (r"\bpandas\b",                              "pandas"),
    (r"\bnumpy\b",                               "NumPy"),
    (r"\bapache\s*spark\b",                      "Apache Spark"),
    (r"\bapache\s*kafka\b",                      "Apache Kafka"),
    (r"\bkafka\b",                               "Apache Kafka"),
    (r"\bhadoop\b",                              "Hadoop"),
    (r"\bcss\b",                                 "CSS"),
    (r"\bhtml\b",                                "HTML"),
    (r"\brest\s*api[s]?\b",                      "REST APIs"),
    (r"\bgraphql\b",                             "GraphQL"),
    (r"\bwebpack\b",                             "Webpack"),
    (r"^reading comprehension$",                 "Reading Comprehension"),
    (r"^active listening$",                      "Active Listening"),
    (r"^complex problem solving$",               "Complex Problem Solving"),
    (r"^critical thinking$",                     "Critical Thinking"),
    (r"^programming$",                           "Programming"),
    (r"^systems analysis$",                      "Systems Analysis"),
    (r"^systems evaluation$",                    "Systems Evaluation"),
    (r"^judgment and decision making$",          "Decision Making"),
    (r"^time management$",                       "Time Management"),
    (r"^active learning$",                       "Active Learning"),
    (r"^technology design$",                     "Technology Design"),
    (r"^troubleshooting$",                       "Troubleshooting"),
    (r"^quality control analysis$",              "Quality Control Analysis"),
    (r"^operations analysis$",                   "Operations Analysis"),
    (r"^writing$",                               "Technical Writing"),
    (r"^speaking$",                              "Communication"),
    (r"^monitoring$",                            "Monitoring"),
    (r"^coordination$",                          "Coordination"),
    (r"^instructing$",                           "Instructing"),
    (r"^mathematics$",                           "Mathematics"),
]

_ALIAS_RE = [(re.compile(p, re.IGNORECASE), r) for p, r in _RAW_ALIASES]


def normalize_skill_name(raw: str) -> str:
    s = raw.strip()
    for pattern, replacement in _ALIAS_RE:
        if pattern.search(s):
            return replacement
    s = re.sub(r"\s+", " ", s).strip()
    words = []
    for w in s.split():
        words.append(w if (w.isupper() and len(w) > 1) else w.capitalize())
    return " ".join(words)


def im_to_level(score: float) -> str:
    if score < 2.50:
        return "beginner"
    if score < 3.75:
        return "intermediate"
    return "advanced"


# ── Loaders ───────────────────────────────────────────────────────────────

def load_esco_role_skills(occupations, relations, esco_label):
    label_lc = esco_label.lower().strip()
    match = occupations[occupations["preferredLabel"].str.lower().str.strip() == label_lc]
    if match.empty:
        print(f"    [ESCO] No exact match for '{esco_label}'; trying partial …")
        match = occupations[
            occupations["preferredLabel"].str.lower().str.contains(
                re.escape(label_lc), na=False
            )
        ]
    if match.empty:
        print(f"    [ESCO] WARNING: '{esco_label}' not found.")
        return {}

    uri       = match.iloc[0]["conceptUri"]
    role_rels = relations[relations["occupationUri"] == uri]
    result: dict[str, str] = {}

    for _, row in role_rels.iterrows():
        raw      = str(row.get("skillLabel", "")).strip()
        rel_type = str(row.get("relationType", "optional")).strip().lower()
        if not raw or raw == "nan":
            continue
        canonical = normalize_skill_name(raw)
        priority  = "essential" if rel_type == "essential" else "optional"
        if result.get(canonical) != "essential":
            result[canonical] = priority

    return result


def load_onet_cognitive(onet_skills, soc_codes):
    df = onet_skills[
        (onet_skills["O*NET-SOC Code"].isin(soc_codes)) &
        (onet_skills["Scale ID"] == "IM") &
        (~onet_skills["Recommend Suppress"].str.upper().fillna("N").eq("Y"))
    ].copy()
    df["Data Value"] = pd.to_numeric(df["Data Value"], errors="coerce")
    df.dropna(subset=["Data Value"], inplace=True)

    averaged = df.groupby("Element Name")["Data Value"].mean()
    result: dict[str, float] = {}
    for element, score in averaged.items():
        canonical = normalize_skill_name(str(element))
        result[canonical] = round(float(score), 4)
    return result


def load_onet_tech(onet_tech, soc_codes):
    df = onet_tech[onet_tech["O*NET-SOC Code"].isin(soc_codes)].copy()
    df["Hot Technology"] = df["Hot Technology"].fillna("N").str.upper().str.strip()
    df["In Demand"]      = df["In Demand"].fillna("N").str.upper().str.strip()
    df["_score"] = df.apply(
        lambda r: TECH_FLAG_SCORE.get((r["Hot Technology"], r["In Demand"]), 1.5),
        axis=1,
    )
    averaged = df.groupby("Example")["_score"].mean()
    result: dict[str, float] = {}
    for example, score in averaged.items():
        canonical = normalize_skill_name(str(example))
        if result.get(canonical, 0.0) < score:
            result[canonical] = round(float(score), 4)
    return result


# ── Merge ──────────────────────────────────────────────────────────────────

def merge_role(esco_priority, onet_cog, onet_tech):
    all_skills = set(esco_priority) | set(onet_cog) | set(onet_tech)
    subskills: list[str] = []
    levels:    dict[str, str] = {}
    priority:  dict[str, str] = {}

    for skill in all_skills:
        score_from_onet = max(onet_cog.get(skill, 0.0), onet_tech.get(skill, 0.0))
        if score_from_onet > 0.0:
            score = score_from_onet
        elif esco_priority.get(skill) == "essential":
            score = ESCO_ESSENTIAL_SCORE
        else:
            score = ESCO_OPTIONAL_SCORE

        if score < IMPORTANCE_THRESHOLD:
            continue

        level = im_to_level(score)
        prio  = esco_priority.get(skill) or ("essential" if score >= 4.0 else "optional")

        subskills.append(skill)
        levels[skill]   = level
        priority[skill] = prio

    subskills.sort(key=lambda s: (0 if priority[s] == "essential" else 1, s.lower()))
    return subskills, levels, priority


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("Curated Skill Graph  —  Build Pipeline")
    print("=" * 60)

    print("\n[1/3] Loading raw data files …")
    esco_occupations = pd.read_csv(
        os.path.join(RAW_DIR, "esco_occupations.csv"), low_memory=False, dtype=str
    )
    esco_relations = pd.read_csv(
        os.path.join(RAW_DIR, "esco_occupation_skills.csv"), low_memory=False, dtype=str
    )
    onet_skills = pd.read_csv(
        os.path.join(RAW_DIR, "onet_skills.csv"), sep="\t", low_memory=False, dtype=str
    )
    onet_tech = pd.read_csv(
        os.path.join(RAW_DIR, "onet_tech_skills.csv"), sep="\t", low_memory=False, dtype=str
    )
    print("    All files loaded.")

    print("\n[2/3] Processing roles …")
    graph: dict = {}

    for role_key, esco_label, cog_socs, tech_socs in TARGET_ROLES:
        print(f"\n  ── {role_key}")

        esco_prio  = load_esco_role_skills(esco_occupations, esco_relations, esco_label)
        cog_scores = load_onet_cognitive(onet_skills, cog_socs)
        tech_scores = load_onet_tech(onet_tech, tech_socs)

        print(f"    ESCO skills: {len(esco_prio)}  |  O*NET cog: {len(cog_scores)}  |  O*NET tech: {len(tech_scores)}")

        subskills, levels, prio_map = merge_role(esco_prio, cog_scores, tech_scores)
        print(f"    Merged subskills: {len(subskills)}")

        if not subskills:
            print(f"    WARNING: No skills for '{role_key}' — skipping.")
            continue

        graph[role_key] = {"subskills": subskills, "levels": levels, "priority": prio_map}

    print(f"\n[3/3] Writing output → {OUT_PATH}")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=2, ensure_ascii=False)

    print("\n✓  role_graph.json generated.")
    for r, d in graph.items():
        essential = sum(1 for p in d["priority"].values() if p == "essential")
        print(f"   {r:<30}  {len(d['subskills']):>3} skills  ({essential} essential)")


if __name__ == "__main__":
    main()
