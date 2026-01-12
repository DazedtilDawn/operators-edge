#!/usr/bin/env python3
"""
Import Analyzer - Parse Python files for import statements.

Extracts import relationships from Python source files using AST parsing.
Generates a dependency graph showing which files import which others.

Usage:
    python3 tools/import_analyzer.py [project_root]

Output:
    .proof/import_graph.json - edges between files based on imports
"""

import ast
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional


def parse_imports(file_path: Path) -> List[Dict]:
    """
    Parse a Python file and extract all import statements.

    Returns list of dicts with:
        - module: the imported module name
        - names: specific names imported (for 'from X import Y')
        - type: 'import' or 'from_import'
    """
    imports = []

    try:
        source = file_path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        print(f"  Syntax error in {file_path}: {e}")
        return []
    except Exception as e:
        print(f"  Error reading {file_path}: {e}")
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    'module': alias.name,
                    'names': [],
                    'type': 'import',
                    'alias': alias.asname
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            # Handle relative imports
            if node.level > 0:
                module = '.' * node.level + module
            imports.append({
                'module': module,
                'names': [alias.name for alias in node.names],
                'type': 'from_import',
                'level': node.level  # 0 = absolute, 1+ = relative
            })

    return imports


def module_to_file_path(module: str, project_files: Set[str], source_file: Path, project_root: Path) -> Optional[str]:
    """
    Convert a module name to a file path, if it exists in the project.

    Handles:
        - Direct module names (e.g., 'tools.proof_visualizer' -> 'tools/proof_visualizer.py')
        - Relative imports (e.g., '.utils' from 'tools/foo.py' -> 'tools/utils.py')
        - Package imports (e.g., 'mypackage' -> 'mypackage/__init__.py')

    Returns None if the module is external (not in project).
    """
    if not module:
        return None

    # Handle relative imports
    if module.startswith('.'):
        # Count the dots
        level = len(module) - len(module.lstrip('.'))
        relative_module = module.lstrip('.')

        # Go up 'level' directories from source file
        base_dir = source_file.parent
        for _ in range(level - 1):  # -1 because first dot means current package
            base_dir = base_dir.parent

        if relative_module:
            candidate = base_dir / relative_module.replace('.', '/')
        else:
            candidate = base_dir
    else:
        # Absolute import
        candidate = project_root / module.replace('.', '/')

    # Try as direct file
    py_path = str(candidate) + '.py'
    if py_path in project_files:
        return py_path

    # Try as package (__init__.py)
    init_path = str(candidate / '__init__.py')
    if init_path in project_files:
        return init_path

    # Try relative to project root variations
    for proj_file in project_files:
        # Check if module name appears in file path
        if module.replace('.', '/') in proj_file or module.replace('.', '_') in proj_file:
            if proj_file.endswith('.py'):
                return proj_file

    return None


def analyze_project(project_root: Path, exclude_patterns: List[str] = None) -> Dict:
    """
    Analyze all Python files in a project and build an import graph.

    Returns:
        {
            'nodes': [{'id': 'file.py', 'name': 'file.py', 'path': 'full/path'}],
            'edges': [{'source': 'a.py', 'target': 'b.py', 'type': 'import', 'weight': 1}],
            'stats': {'total_files': N, 'total_edges': N, 'external_imports': N}
        }
    """
    if exclude_patterns is None:
        exclude_patterns = [
            'venv', 'env', '.venv', '__pycache__',
            'node_modules', '.git', 'build', 'dist',
            '.egg-info', 'site-packages'
        ]

    # Find all Python files
    py_files = []
    for py_file in project_root.rglob('*.py'):
        # Skip excluded directories
        skip = False
        for pattern in exclude_patterns:
            if pattern in str(py_file):
                skip = True
                break
        if not skip:
            py_files.append(py_file)

    print(f"Found {len(py_files)} Python files")

    # Build set of project file paths for matching
    project_files = {str(f) for f in py_files}
    project_files_relative = {str(f.relative_to(project_root)) for f in py_files}

    # Analyze each file
    nodes = []
    edges = []
    edge_set = set()  # Track unique edges
    external_imports = set()

    for py_file in py_files:
        rel_path = str(py_file.relative_to(project_root))
        file_name = py_file.name

        nodes.append({
            'id': rel_path,
            'name': file_name,
            'path': str(py_file)
        })

        imports = parse_imports(py_file)

        for imp in imports:
            target = module_to_file_path(
                imp['module'],
                project_files | project_files_relative,
                py_file,
                project_root
            )

            if target:
                # Normalize target to relative path
                try:
                    target_rel = str(Path(target).relative_to(project_root))
                except ValueError:
                    target_rel = target

                # Ensure target exists in our file set
                if target_rel in project_files_relative or target in project_files:
                    edge_key = (rel_path, target_rel if target_rel in project_files_relative else target)
                    if edge_key not in edge_set:
                        edge_set.add(edge_key)
                        edges.append({
                            'source': rel_path,
                            'target': target_rel if target_rel in project_files_relative else target,
                            'type': imp['type'],
                            'module': imp['module'],
                            'weight': 1
                        })
            else:
                # External import
                external_imports.add(imp['module'])

    # Merge duplicate edges (same source/target) by increasing weight
    merged_edges = {}
    for edge in edges:
        key = (edge['source'], edge['target'])
        if key in merged_edges:
            merged_edges[key]['weight'] += 1
        else:
            merged_edges[key] = edge

    edges = list(merged_edges.values())

    print(f"Found {len(edges)} internal import edges")
    print(f"Found {len(external_imports)} unique external imports")

    return {
        'nodes': nodes,
        'edges': edges,
        'stats': {
            'total_files': len(py_files),
            'total_edges': len(edges),
            'external_imports': len(external_imports)
        },
        'external': sorted(list(external_imports))[:20]  # Top 20 external deps
    }


def main():
    """Main entry point."""
    # Determine project root
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path.cwd()

    print(f"Analyzing imports in: {project_root}")

    # Run analysis
    result = analyze_project(project_root)

    # Save to .proof directory
    proof_dir = project_root / '.proof'
    proof_dir.mkdir(exist_ok=True)

    output_path = proof_dir / 'import_graph.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\nSaved import graph to {output_path}")
    print(f"Stats: {result['stats']['total_files']} files, {result['stats']['total_edges']} edges")

    return result


if __name__ == '__main__':
    main()
