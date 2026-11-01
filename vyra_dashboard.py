"""
VYRA Application Intelligence Dashboard
Run from your repository root:
    pip install streamlit plotly pandas
    streamlit run vyra_dashboard.py

Scans Python source locally. Static indicators are not proof of runtime success.
"""
from __future__ import annotations
import ast, os, math
from pathlib import Path
from collections import Counter
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="VYRA | Application Intelligence", page_icon="✦", layout="wide")
SKIP = {".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache",
        ".pytest_cache", "staticfiles", "media", "chroma_db", "vector_db",
        "site-packages", "dist", "build"}
RAG_TERMS = ("rag", "retriev", "embedding", "vector", "chroma", "faiss", "chunk",
             "splitter", "document", "loader", "knowledge", "semantic", "context")
LLM_TERMS = ("claude", "anthropic", "openai", "llm", "generate_response", "prompt")

def dotted(n):
    if isinstance(n, ast.Name): return n.id
    if isinstance(n, ast.Attribute): return dotted(n.value) + "." + n.attr
    if isinstance(n, ast.Call): return dotted(n.func)
    return ""

def scan(root):
    records = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for name in names:
            if not name.endswith(".py") or name == "manage.py": continue
            p = Path(base) / name
            rel = p.relative_to(root).as_posix()
            try:
                source = p.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source)
                imports, classes, functions = [], [], []
                for n in ast.walk(tree):
                    if isinstance(n, ast.Import):
                        imports.extend(a.name for a in n.names)
                    elif isinstance(n, ast.ImportFrom) and n.module:
                        imports.append("." * n.level + n.module)
                for n in tree.body:
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions.append({"name": n.name, "line": n.lineno})
                    elif isinstance(n, ast.ClassDef):
                        methods = [x.name for x in n.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]
                        classes.append({"name": n.name, "line": n.lineno,
                                        "bases": [dotted(b) for b in n.bases], "methods": methods})
                records.append({"file": rel, "lines": len(source.splitlines()),
                                "imports": imports, "classes": classes,
                                "functions": functions, "error": ""})
            except Exception as e:
                records.append({"file": rel, "lines": 0, "imports": [],
                                "classes": [], "functions": [], "error": str(e)})
    return records

def source_matches(root, records, term):
    rows = []
    for r in records:
        try: lines = (root / r["file"]).read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception: continue
        for i, line in enumerate(lines, 1):
            if term.lower() in line.lower():
                rows.append({"File": r["file"], "Line": i, "Source": line.strip()[:250]})
    return pd.DataFrame(rows)

st.title("✦ VYRA | Application Intelligence")
st.caption("A live, source-code-derived view of VYRA's architecture and capabilities.")
default_root = str(Path.cwd())
with st.sidebar:
    st.subheader("Repository")
    root_text = st.text_input("Project root", st.session_state.get("root", default_root))
    if st.button("Scan repository", type="primary"):
        st.session_state["root"] = root_text
        st.rerun()

ROOT = Path(st.session_state.get("root", root_text)).expanduser().resolve()
if not ROOT.is_dir():
    st.error(f"Folder not found: {ROOT}")
    st.stop()
with st.spinner("Scanning Python source..."):
    FILES = scan(ROOT)
if not FILES:
    st.warning("No Python files found. Set the repository root to your VYRA folder.")
    st.stop()

total_classes = sum(len(x["classes"]) for x in FILES)
total_functions = sum(len(x["functions"]) + sum(len(c["methods"]) for c in x["classes"]) for x in FILES)
parse_errors = sum(bool(x["error"]) for x in FILES)
def module(path):
    return path.removesuffix(".py").replace("/", ".")

# Static inventories
class_rows, test_rows, rag_rows, url_rows, edge_rows = [], [], [], [], []
known = {module(x["file"]) for x in FILES}
for f in FILES:
    for c in f["classes"]:
        class_rows.append({"File": f["file"], "Class": c["name"], "Line": c["line"],
                           "Bases": ", ".join(c["bases"]), "Methods": len(c["methods"]),
                           "Method names": ", ".join(c["methods"])})
    if "/test" in f["file"] or f["file"].startswith("tests/") or f["file"].endswith("tests.py"):
        tests = []
        for c in f["classes"]:
            methods = [m for m in c["methods"] if m.startswith("test")]
            if methods: test_rows.append({"File": f["file"], "Class": c["name"],
                                          "Test methods": len(methods), "Names": ", ".join(methods)})
        top = [x["name"] for x in f["functions"] if x["name"].startswith("test")]
        if top: test_rows.append({"File": f["file"], "Class": "(module-level)",
                                  "Test methods": len(top), "Names": ", ".join(top)})
    terms = (f["file"] + " " + " ".join(f["imports"]) + " " +
             " ".join(c["name"] for c in f["classes"]) + " " +
             " ".join(x["name"] for x in f["functions"])).lower()
    rt = [x for x in RAG_TERMS if x in terms]
    lt = [x for x in LLM_TERMS if x in terms]
    if rt or lt: rag_rows.append({"Source file": f["file"], "RAG indicators": ", ".join(rt),
                                  "LLM indicators": ", ".join(lt), "Lines": f["lines"]})
    if f["file"].endswith("urls.py"):
        try:
            tree = ast.parse((ROOT / f["file"]).read_text(encoding="utf-8", errors="replace"))
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and dotted(n.func).split(".")[-1] in {"path", "re_path", "include"}:
                    route = n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else "(dynamic / included)"
                    target = dotted(n.args[1]) if len(n.args) > 1 else "(see source)"
                    url_rows.append({"URL config": f["file"], "Route": route, "Target": target, "Line": n.lineno})
        except Exception: pass
    for imp in f["imports"]:
        normalized = imp.lstrip(".")
        match = next((k for k in known if normalized == k or k.endswith("." + normalized)
                      or normalized.endswith("." + k)), None)
        if match: edge_rows.append({"From": module(f["file"]), "To": match})

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Python files", len(FILES))
c2.metric("Classes", total_classes)
c3.metric("Functions / methods", total_functions)
c4.metric("URL patterns", len(url_rows))
c5.metric("Test methods found", sum(x["Test methods"] for x in test_rows))
st.caption(f"Source: `{ROOT}` · Parse errors: {parse_errors}")

tabs = st.tabs(["Overview", "Architecture", "RAG & AI", "API routes", "Data models", "Tests", "Source explorer"])
with tabs[0]:
    st.subheader("Codebase composition")
    counts = Counter((Path(x["file"]).parts[0] if len(Path(x["file"]).parts)>1 else "(root)") for x in FILES)
    df = pd.DataFrame([{"Directory": k, "Python files": v} for k,v in counts.most_common()])
    a,b = st.columns(2)
    with a:
        st.plotly_chart(px.bar(df.head(20), x="Python files", y="Directory", orientation="h",
                               title="Python files by directory").update_layout(height=500,
                               yaxis={"categoryorder":"total ascending"}), use_container_width=True)
    with b:
        st.plotly_chart(px.pie(df.head(12), names="Directory", values="Python files",
                               title="Source distribution").update_layout(height=500), use_container_width=True)
    st.subheader("Largest source files")
    st.dataframe(pd.DataFrame([{"File":x["file"],"Lines":x["lines"],
                    "Classes":len(x["classes"]),"Functions":len(x["functions"])} for x in FILES])
                 .sort_values("Lines",ascending=False).head(20), use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("Internal module dependency map")
    st.caption("Edges are inferred from imports resolving to files inside this repository; this is not a runtime call graph.")
    edges = pd.DataFrame(edge_rows).drop_duplicates() if edge_rows else pd.DataFrame()
    if edges.empty: st.info("No internal import edges resolved.")
    else:
        degree = Counter(edges["From"].tolist()+edges["To"].tolist())
        nodes = sorted({n for n,_ in degree.most_common(30)})
        pos = {n:(math.cos(2*math.pi*i/len(nodes)),math.sin(2*math.pi*i/len(nodes))) for i,n in enumerate(nodes)}
        view = edges[edges["From"].isin(nodes)&edges["To"].isin(nodes)]
        ex,ey=[],[]
        for _,e in view.iterrows():
            x0,y0=pos[e["From"]]; x1,y1=pos[e["To"]]; ex += [x0,x1,None]; ey += [y0,y1,None]
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=ex,y=ey,mode="lines",line=dict(width=1,color="rgba(130,140,170,.4)"),hoverinfo="none"))
        fig.add_trace(go.Scatter(x=[pos[n][0] for n in nodes],y=[pos[n][1] for n in nodes],
            mode="markers+text",text=[n.split(".")[-1] for n in nodes],customdata=nodes,
            textposition="top center",marker=dict(size=[13+degree[n]*2 for n in nodes]),
            hovertemplate="%{customdata}<extra></extra>"))
        fig.update_layout(height=650,showlegend=False,xaxis_visible=False,yaxis_visible=False,
                          paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig,use_container_width=True)
        st.dataframe(edges,use_container_width=True,hide_index=True)

with tabs[2]:
    st.subheader("RAG and AI source inventory")
    st.caption("Detected source references are not proof that ingestion or retrieval has executed successfully.")
    rdf=pd.DataFrame(rag_rows)
    if rdf.empty: st.info("No RAG / LLM indicators detected.")
    else:
        st.metric("Files with RAG / LLM indicators",len(rdf))
        st.dataframe(rdf,use_container_width=True,hide_index=True)
    q=st.text_input("Find a pipeline component in source", "retrieve_context")
    if q:
        matches=source_matches(ROOT,FILES,q)
        st.dataframe(matches,use_container_width=True,hide_index=True)
    st.warning("A functional RAG proof requires a real document to be indexed, relevant chunks retrieved from the vector store, and those chunks passed into response generation.")

with tabs[3]:
    st.subheader("Django URL declarations")
    urls=pd.DataFrame(url_rows)
    if urls.empty: st.info("No URL declarations found in urls.py files.")
    else: st.dataframe(urls,use_container_width=True,hide_index=True)

with tabs[4]:
    st.subheader("Model and data layer")
    models=[r for r in class_rows if "models.py" in r["File"] or "Model" in r["Bases"]]
    if models: st.dataframe(pd.DataFrame(models),use_container_width=True,hide_index=True)
    else: st.info("No model classes detected automatically.")
    st.caption("Model relationships and constraints should be confirmed in source.")

with tabs[5]:
    st.subheader("Test inventory")
    tdf=pd.DataFrame(test_rows)
    if tdf.empty: st.info("No test methods found in conventional test files.")
    else:
        st.dataframe(tdf,use_container_width=True,hide_index=True)
        st.metric("Test methods discovered",int(tdf["Test methods"].sum()))
    st.error("Discovered tests are not passing tests. Retain actual test output or CI evidence.")
    st.code("python manage.py test chatbot.tests.test_user_journey -v 2",language="bash")

with tabs[6]:
    q=st.text_input("Search source for a function, class, setting, or keyword")
    if q: st.dataframe(source_matches(ROOT,FILES,q),use_container_width=True,hide_index=True)
    st.subheader("Class and method index")
    st.dataframe(pd.DataFrame(class_rows),use_container_width=True,hide_index=True)
    errors=pd.DataFrame([{"File":x["file"],"Error":x["error"]} for x in FILES if x["error"]])
    if errors.empty: st.success("All scanned Python files parsed successfully.")
    else: st.dataframe(errors,use_container_width=True,hide_index=True)

st.divider()
st.caption("VYRA Application Intelligence · Local source scan · No source code is uploaded.")
