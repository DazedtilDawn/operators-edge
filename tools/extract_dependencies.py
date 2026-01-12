#!/usr/bin/env python3
"""
Extract Dependencies - Generate dependencies.json for Explorer Mode

Builds a dependency graph from:
1. Python imports (static analysis)
2. File co-occurrence in session log (behavioral analysis)

Output: .proof/dependencies.json

Usage:
    python3 tools/extract_dependencies.py
"""
import ast
import json
import os
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple


def extract_imports(file_path: Path) -> List[Tuple[str, str]]:
    """Extract import statements from a Python file."""
    imports = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((str(file_path), alias.name.split('.')[0]))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split('.')[0]
                    imports.append((str(file_path), module))
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
        pass
    return imports


def get_local_modules(project_root: Path) -> Set[str]:
    """Get set of local module names in the project."""
    modules = set()
    for item in project_root.iterdir():
        if item.is_dir() and not item.name.startswith('_'):
            if (item / '__init__.py').exists() or any(item.glob('*.py')):
                modules.add(item.name)
        elif item.suffix == '.py':
            modules.add(item.stem)
    return modules


def extract_file_from_preview(preview) -> str:
    """Extract file name from input_preview (handles dict or string)."""
    if isinstance(preview, dict):
        # Direct dict format: {"file": "path/to/file.py"}
        for key in ['file', 'file_path', 'path']:
            if key in preview:
                return Path(str(preview[key])).name
    elif isinstance(preview, str):
        # String format - look for file paths
        # Pattern 1: 'file': '/path/to/file.py'
        match = re.search(r"['\"]?(?:file|file_path|path)['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", preview, re.I)
        if match:
            return Path(match.group(1)).name
        # Pattern 2: any path ending in common extensions
        match = re.search(r'[/\\]?([a-zA-Z0-9_-]+\.(?:py|yaml|yml|json|md|txt|html|js|css))', preview)
        if match:
            return match.group(1)
    return None


def load_session_cooccurrence(project_root: Path) -> Dict[Tuple[str, str], int]:
    """Build co-occurrence edges from session log - files touched together."""
    session_log = project_root / '.proof' / 'session_log.jsonl'
    cooccurrence = defaultdict(int)

    if not session_log.exists():
        return cooccurrence

    # Group events by 5-minute windows
    window_files = defaultdict(set)

    try:
        with open(session_log) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    preview = entry.get('input_preview', '')
                    file_name = extract_file_from_preview(preview)
                    if file_name:
                        # Use timestamp for windowing (5-min buckets)
                        ts = entry.get('timestamp', '')[:15]  # YYYY-MM-DDTHH:M
                        window_files[ts].add(file_name)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    # Create edges between files in same window
    for window, files in window_files.items():
        files_list = list(files)
        for i, f1 in enumerate(files_list):
            for f2 in files_list[i+1:]:
                key = tuple(sorted([f1, f2]))
                cooccurrence[key] += 1

    return cooccurrence


def build_dependency_graph(project_root: Path) -> Dict:
    """Build dependency graph from Python files and session data."""
    edges = []
    nodes = defaultdict(lambda: {'type': 'file', 'imports': 0, 'imported_by': 0, 'cooccur': 0})
    local_modules = get_local_modules(project_root)

    # Directories to include (including .claude for hooks)
    include_patterns = ['tools', '.claude/hooks', '.claude/skills', '.claude/agents']
    skip_dirs = {'.git', '__pycache__', 'venv', 'env', '.venv', 'node_modules', 'dist'}

    for root, dirs, files in os.walk(project_root):
        rel_root = Path(root).relative_to(project_root)

        # Skip unwanted directories
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for file in files:
            # Include Python, YAML, JSON, and Markdown files
            if file.endswith(('.py', '.yaml', '.yml', '.json', '.md')):
                file_path = Path(root) / file
                rel_path = file_path.relative_to(project_root)

                source_name = str(rel_path)
                nodes[source_name]['type'] = 'file'
                nodes[source_name]['path'] = str(rel_path)
                nodes[source_name]['dir'] = str(rel_path.parent) if str(rel_path.parent) != '.' else 'root'
                nodes[source_name]['ext'] = file_path.suffix

                # Extract Python imports
                if file.endswith('.py'):
                    imports = extract_imports(file_path)
                    for source, target in imports:
                        if target in local_modules:
                            nodes[source_name]['imports'] += 1
                            nodes[target]['type'] = 'module'
                            nodes[target]['imported_by'] += 1
                            edges.append({
                                'source': source_name,
                                'target': target,
                                'type': 'imports'
                            })

    # Add co-occurrence edges from session log
    cooccurrence = load_session_cooccurrence(project_root)
    node_names = {Path(n).name: n for n in nodes.keys()}

    for (f1, f2), count in cooccurrence.items():
        if count >= 2:  # Only include if co-occurred at least twice
            source = node_names.get(f1)
            target = node_names.get(f2)
            if source and target and source != target:
                nodes[source]['cooccur'] += count
                nodes[target]['cooccur'] += count
                edges.append({
                    'source': source,
                    'target': target,
                    'type': 'cooccur',
                    'weight': count
                })

    # Build final structure
    return {
        'nodes': [
            {
                'id': name,
                'name': Path(name).name,
                'type': data['type'],
                'path': data.get('path', name),
                'dir': data.get('dir', 'root'),
                'ext': data.get('ext', ''),
                'imports': data['imports'],
                'imported_by': data['imported_by'],
                'cooccur': data['cooccur']
            }
            for name, data in nodes.items()
        ],
        'edges': edges,
        'stats': {
            'total_files': len(nodes),
            'total_edges': len(edges),
            'import_edges': sum(1 for e in edges if e['type'] == 'imports'),
            'cooccur_edges': sum(1 for e in edges if e['type'] == 'cooccur')
        }
    }


def main():
    project_root = Path(__file__).parent.parent
    output_path = project_root / '.proof' / 'dependencies.json'

    print("Extracting dependencies...")
    graph = build_dependency_graph(project_root)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(graph, f, indent=2)

    print(f"Generated {output_path}")
    print(f"  Files: {graph['stats']['total_files']}")
    print(f"  Import edges: {graph['stats']['import_edges']}")
    print(f"  Co-occur edges: {graph['stats']['cooccur_edges']}")
    print(f"  Total edges: {graph['stats']['total_edges']}")


if __name__ == '__main__':
    main()
