# Port experimental lproj: Linux 3.4.0 para 3.18.140

**A migração ainda não está concluída. Esta branch contém a ferramenta Python 3,
uma resolução revisada do Makefile e o diagnóstico reproduzível. O kernel
versionado nesta branch continua em 3.4.0. O código integrado do 3.18 fica em
uma nova árvore de trabalho, com conflitos explicitamente preservados no Git.**

A integração real encontrou **1.231 arquivos em conflito**. A resolução do
Makefile principal por Python reduziu esse total para **1.230**. Não houve
compilação nem teste em aparelho. A ferramenta bloqueou a compilação antes de
executar `make`, porque ainda existem entradas não resolvidas no índice.

## Revisões fixadas

| Papel | Origem | Commit |
| --- | --- | --- |
| Kernel LG | RodrigoAyuso/lge-kernel-lproj, lineage-15.1 | `1327a704761cfa043f94e4fe6d1b35e604860b2a` |
| Base de comparação | torvalds/linux, v3.4 | `76e10d158efb6d4516018846f60c2ab5501900bc` |
| Alvo | gregkh/linux, v3.18.140 | `6b1ae527b1fdee86e81da0cb26ced75731c6c0fa` |

A árvore upstream v3.4 é uma **base de comparação explícita**, não uma
ancestralidade do histórico LG que tenha sido comprovada. O uso dessa base
permite comparar o delta do fabricante com o upstream 3.18, inclusive em clones
rasos. Um merge textual sem conflito ainda pode conter incompatibilidades de
API e de comportamento; exige revisão e compilação.

## Reproduzir com Python 3

Execute da raiz desta branch, com Git que ofereça
`merge-tree --write-tree --merge-base` (validado com Git 2.52.0 e Python 3.12.14).
A ferramenta usa apenas a biblioteca padrão de Python e o executável Git.
O clone deve conter o commit LG fixado acima. Se ele não estiver disponível,
obtenha-o com `git fetch --depth=1 origin 1327a704761cfa043f94e4fe6d1b35e604860b2a`.

```sh
python3 scripts/port_to_318.py fetch
python3 scripts/port_to_318.py audit --report ../audit-3.18.140.json
python3 scripts/port_to_318.py prepare --worktree ../lge-kernel-3.18.140 --branch port/linux-3.18.140 --report ../audit-3.18.140.json
python3 scripts/port_to_318.py edit --worktree ../lge-kernel-3.18.140 --manifest scripts/port_to_318.makefile.json
python3 scripts/port_to_318.py status --worktree ../lge-kernel-3.18.140
```

`fetch` verifica os commits dos dois tags upstream. O fetch é raso para o diagnóstico local; o histórico upstream
necessário deverá ser completado antes de publicar um futuro merge do kernel. `audit` cria objetos Git e o
relatório; não edita o checkout. `prepare` exige um caminho e uma branch novos,
materializa a árvore integrada e restaura os estágios de conflito do índice.
O checkout original e suas alterações locais são preservados. O estado permite
usar normalmente `git diff`, `git ls-files -u`, `git merge --abort` e, após
resolver e validar o port, `git commit`. O eventual commit de merge terá o
commit LG e o commit upstream como pais. Nenhum comando da ferramenta faz push.

O manifesto revisado atua somente no Makefile principal. Resolve seus quatro
blocos em conflito e remove os ajustes remanescentes de otimização e do wrapper
Python 2 do fabricante. O resultado corresponde byte a byte ao Makefile do
commit 3.18.140 fixado. As regras de CPU/ABI ficam sob o controle dos Makefiles
da arquitetura; o port desses Makefiles ainda está pendente.

As substituições feitas pelo subcomando `edit` são edições Python, com SHA-256
do arquivo completo antes e depois. Cada trecho deve ocorrer exatamente uma
vez. Todas as precondições são verificadas antes da primeira gravação. Arquivos
com marcadores de conflito remanescentes são recusados. A ferramenta adiciona
ao índice apenas os arquivos listados no manifesto, após concluir as edições.
Outras resoluções devem ser revisadas e expressas em novos manifestos com a
mesma estrutura. Não há seleção automática global da versão LG ou upstream.

## Bloqueios observados

O [audit.json](audit.json) inclui a lista completa de conflitos, a configuração
original de cada variante e os símbolos de hardware ausentes do upstream.
Entre eles estão `ARCH_MSM7X27A`, `MACH_LGE`, `MSM_KGSL`, `FB_MSM_MDP303` e
`MSM7X27A_AUDIO`. Copiar um defconfig para o 3.18 oficial não recria esse suporte.

| Grupo | Arquivos inicialmente em conflito |
| --- | ---: |
| drivers/video | 247 |
| drivers/media | 227 |
| arch/arm | 137 |
| include/linux | 90 |
| drivers/usb | 56 |

Também há conflitos em memória, escalonamento, arquivos, rede, segurança e
outros subsistemas. O relatório agrupa por caminho, não por dificuldade ou
quantidade de trabalho. A plataforma MSM7x27A e as interfaces dos drivers LG
precisam ser adaptadas antes de considerar o kernel compilável.

As sete variantes originais são preservadas para orientar o port:

| Aparelho | Defconfig |
| --- | --- |
| L1 II | lineage_v1_defconfig |
| L3 II | lineage_vee3_defconfig |
| L5 com NFC | lineage_m4_defconfig |
| L5 sem NFC | lineage_m4_nonfc_defconfig |
| L7 com NFC | lineage_u0_defconfig |
| L7 sem NFC | lineage_u0_nonfc_defconfig |
| L7 com câmera de 8 MP | lineage_u0_8m_defconfig |

A escolha do primeiro modelo deve preceder a validação das opções de placa.
Depois é necessário resolver os conflitos da plataforma e dos subsistemas,
regenerar a configuração, compilar `zImage` e módulos e testar o boot e os
periféricos no aparelho. Nenhuma dessas validações do kernel foi concluída.

## Validação da ferramenta

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_port_to_318.py' -v
```

Onze testes com repositórios Git reais validam preservação do checkout sujo,
retomada e cancelamento do merge, proteção de caminhos existentes, precondições
de edição, criação posterior de commit com os dois pais e bloqueio de build.
Esses testes validam a ferramenta; não validam o kernel.

Após resolver todos os conflitos, a compilação pode ser tentada com um
compilador ARM de 32 bits compatível já instalado. Exemplo de interface
(ajuste o prefixo e o defconfig ao ambiente e ao aparelho):

```sh
python3 scripts/port_to_318.py build --worktree ../lge-kernel-3.18.140 --defconfig lineage_v1_defconfig --cross-compile arm-eabi- --output ../build-3.18.140-v1
```

O comando exige saída vazia fora da árvore de fontes, recusa marcadores de
conflito nos fontes e verifica se a regeneração do defconfig descartou símbolos
críticos do aparelho. Também exige o alvo upstream fixado como merge pendente
ou ancestral do checkout, para não aceitar uma simples alteração da versão no
Makefile. Salva o log de compilação no diretório de saída. Sucesso
da compilação continua separado da validação em hardware.
