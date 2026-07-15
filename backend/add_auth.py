#!/usr/bin/env python3
"""
Script para adicionar autenticação JWT a todas as rotas.
"""
import re
from pathlib import Path

def add_auth_to_file(filepath):
    """Adiciona `current_user: dict = Depends(get_current_user),` como primeiro parâmetro de cada rota."""
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Padrão para encontrar funções de rota
    # Procura por: def function_name(\n ou def function_name(param)
    pattern = r'(def \w+\(\s*)'
    
    # Se não tem autenticação, adiciona
    if 'current_user: dict = Depends(get_current_user)' not in content:
        # Encontrar todas as funções de rota (que estão depois de @router)
        lines = content.split('\n')
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            result.append(line)
            
            # Se é um decorator de rota
            if '@router.' in line:
                i += 1
                # A próxima linha deve ser `def`
                if i < len(lines) and 'def ' in lines[i]:
                    def_line = lines[i]
                    # Verifica se precisa adicionar autenticação
                    if 'current_user' not in def_line:
                        # Encontra o índice da abertura de parênteses
                        paren_idx = def_line.find('(')
                        if paren_idx != -1:
                            # Adiciona autenticação como primeiro parâmetro
                            indent = len(def_line) - len(def_line.lstrip())
                            new_def = def_line[:paren_idx+1] + '\n' + ' ' * (indent + 4) + 'current_user: dict = Depends(get_current_user),\n' + ' ' * indent
                            
                            # Se há outros parâmetros na mesma linha
                            rest = def_line[paren_idx+1:].strip()
                            if rest and rest != ')':
                                new_def += '    ' + rest
                            
                            result.append(new_def.rstrip() + '\n')
                            i += 1
                            continue
            
            i += 1
        
        content = '\n'.join(result)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Autenticação adicionada a {filepath}")

# Processa todos os arquivos de rotas
routes_dir = Path(__file__).parent / "app" / "api"
for route_file in routes_dir.glob("*.py"):
    if route_file.name not in ['__init__.py', 'auth.py']:
        print(f"Processando {route_file.name}...")
        add_auth_to_file(route_file)

print("\n✅ Todas as rotas foram protegidas com autenticação JWT!")
