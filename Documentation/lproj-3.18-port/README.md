# Port experimental do Vee3 para Linux 3.18.140

O alvo prioritário é o **LG L3 II (Vee3)**, com
`lineage_vee3_defconfig`, `MACH_MSM7X25A_V3`, machine ID **10004** e
`mach/lge/board_v3.h`. O comando de build Python usa esse defconfig por padrão.

**O port ainda está incompleto. O kernel versionado nesta branch continua com
versão 3.4.0 e recebeu as primeiras adaptações de interface do Vee3 para 3.18,
protegidas por versão para manter a compilação de referência. A integração
3.18.140 fica em uma nova árvore de trabalho. Restam 1.228 arquivos em conflito;
não há kernel 3.18 completo compilado nem boot validado.**

O [vee3-progress.json](vee3-progress.json) registra o estado atual, as opções de
hardware exigidas, os hashes dos fontes modificados e o alcance das validações.
O [audit.json](audit.json) preserva o diagnóstico inicial de 1.231 conflitos e
as configurações originais dos aparelhos; seus resultados de ferramenta e
compilador são históricos.

## Alterações do Vee3

- O descritor da placa usa `.init_time = msm_timer_init` no 3.18, mantendo o
  caminho `.timer` da referência 3.4.
- O timer usa `<linux/sched_clock.h>`, callback com retorno `u64` e
  `sched_clock_register()` no 3.18. A frequência e a largura efetiva do contador
  são preservadas. A estrutura `sys_timer` é emitida apenas na referência 3.4.
- O header de timers locais fica condicionado a `CONFIG_LOCAL_TIMERS`; o Vee3
  é uniprocessador. O port dos outros aparelhos não está validado.
- O manifesto dos Makefiles resolve os arquivos principal e ARM para versões
  idênticas ao upstream fixado, removendo a seleção forçada de NEON/vetorização
  e o diretório legado `perfmon` das regras de compilação ARM.
- A configuração Vee3 é verificada contra 25 seleções de hardware, incluindo
  placa, endereço físico, display, GPU, áudio, câmera, touch, sensores, memória,
  Binder e Wi-Fi. `VOLANS_WLAN=m` também é exigido: módulos perdidos na
  regeneração do defconfig não passam despercebidos. Outra placa LG ativa ou
  SMP habilitado fazem a verificação falhar.

São primeiras adaptações do caminho de boot. As demais interfaces do timer,
relógios, IRQs, memória e drivers ainda precisam ser portadas e compiladas na
árvore completa do 3.18.

## Revisões fixadas

| Papel | Origem | Commit |
| --- | --- | --- |
| Kernel LG | RodrigoAyuso/lge-kernel-lproj, lineage-15.1 | `1327a704761cfa043f94e4fe6d1b35e604860b2a` |
| Base de comparação | torvalds/linux, v3.4 | `76e10d158efb6d4516018846f60c2ab5501900bc` |
| Alvo | gregkh/linux, v3.18.140 | `6b1ae527b1fdee86e81da0cb26ced75731c6c0fa` |

O upstream v3.4 é uma base de comparação explícita, não uma ancestralidade do
histórico LG que tenha sido comprovada. Um merge textual sem conflitos ainda
pode conter incompatibilidades de API e comportamento.

## Reproduzir as edições com Python 3

Execute da raiz desta branch. A ferramenta usa a biblioteca padrão de Python e
Git com `merge-tree --write-tree --merge-base` (validado com Python 3.12.14 e
Git 2.52.0). O clone precisa conter o commit LG fixado. Se necessário, obtenha-o
com `git fetch --depth=1 origin 1327a704761cfa043f94e4fe6d1b35e604860b2a`.

```sh
python3 scripts/port_to_318.py fetch
python3 scripts/port_to_318.py prepare --worktree ../lge-kernel-3.18.140 --branch port/linux-3.18.140 --report ../audit-3.18.140.json
python3 scripts/port_to_318.py edit --worktree ../lge-kernel-3.18.140 --manifest scripts/port_to_318.makefile.json
python3 scripts/port_to_318.py edit --worktree ../lge-kernel-3.18.140 --manifest scripts/port_to_318.vee3.json
python3 scripts/port_to_318.py status --worktree ../lge-kernel-3.18.140
```

Use um caminho e uma branch novos para `prepare`. O comando materializa o merge
em outra árvore e mantém os estágios de conflito no índice Git, preservando o
checkout original e suas alterações. Os manifestos exigem SHA-256 antes e
depois e substituições com correspondência única. As precondições de todos os
arquivos são verificadas antes da primeira gravação. Arquivos ainda com
marcadores de conflito são recusados. A ferramenta não faz push nem resolve
conflitos por uma seleção global da versão LG ou upstream.

O estado permite usar `git diff`, `git ls-files -u`, `git merge --abort` e,
depois da revisão e validação do port, `git commit`. O eventual merge terá os
commits LG e upstream como pais. O fetch é raso para o diagnóstico local;
complete o histórico upstream necessário antes de publicar esse futuro merge.
O subcomando `audit --report CAMINHO` continua disponível para refazer apenas
o diagnóstico, sem editar o checkout.

## Verificações realizadas

| Verificação | Resultado e limite |
| --- | --- |
| Testes Python/Git | 15 passaram; validam ferramenta, preservação de arquivos e proteção do perfil Vee3 |
| Defconfig original Vee3 | Gerado na base 3.4; as 25 seleções de hardware passaram na verificação |
| Objetos de referência 3.4 | `timer.o` e `board-msm7x27a_lge.o` compilaram com as alterações |
| Interfaces com headers 3.18 | Probe ARM compilou com `-Werror`; não compila os drivers completos do Vee3 |
| Controle negativo do probe | Código antigo falhou por `setup_sched_clock()` ausente e campo `.timer` removido |
| Kernel completo 3.18 | Não compilado; bloqueado pelos conflitos restantes |
| Boot e periféricos | Não testados em hardware |

O probe usa declarações, callback e descritor extraídos dos fontes modificados,
contra os headers reais de uma árvore upstream 3.18.140 preparada com
`multi_v7_defconfig`. Essa configuração serve apenas à verificação das
interfaces; **não representa uma configuração funcional do Vee3**. O resultado
é um objeto ELF32 ARM EABI5. Ele não executa MMIO nem testa comportamento dos
timers. O controle negativo usa as interfaces do commit LG original.

A compilação de referência 3.4 invocou o compilador diretamente para evitar o
wrapper Python 2 legado, com `CFLAGS_KERNEL=` e `AFLAGS_KERNEL=`. Ela verifica
apenas os dois objetos citados, não a compilação ou o funcionamento do kernel
completo. Na preparação das ferramentas do upstream 3.18, o compilador host
moderno exigiu `HOSTCFLAGS=-O2 -std=gnu89 -fcommon` para o DTC legado.

Foi utilizado o [toolchain do projeto TeamVee](https://github.com/TeamVee/android_prebuilt_toolchains/tree/linaro_gcc),
commit `5743106b17c82d86bebd5c140cbd4cf3d4ee930a`, diretório
`arm-cortex-linux-gnueabi-linaro_4.9.4-2015.06`. O GCC 4.8.0 de referência foi
rejeitado pela verificação de versão do ARM no upstream 3.18; essa proteção não
foi removida.

```sh
python3 -B -m unittest discover -s scripts/tests -p 'test_port_to_318.py' -v
python3 scripts/port_to_318.py check-vee3-config --config CAMINHO_DA_CONFIG_GERADA
```

## Próxima etapa da integração

Resolver os conflitos de `arch/arm/Kconfig`, `arch/arm/mach-msm/Kconfig` e
`arch/arm/mach-msm/Makefile`, integrando as dependências de clock, IRQ e memória
MSM7x27A com o núcleo 3.18. Depois será necessário portar os demais drivers,
regenerar o defconfig Vee3 e compilar `zImage` e módulos antes do teste no
aparelho. O upstream puro não define símbolos como `ARCH_MSM7X27A`,
`MACH_LGE`, `MSM_KGSL`, `FB_MSM_MDP303` ou `MSM7X27A_AUDIO`.

Após resolver todos os conflitos, o comando abaixo permite tentar a
compilação completa. Ajuste o caminho do toolchain ao ambiente:

```sh
python3 scripts/port_to_318.py build --worktree ../lge-kernel-3.18.140 --cross-compile ../toolchains-teamvee/arm-cortex-linux-gnueabi-linaro_4.9.4-2015.06/bin/arm-eabi- --output ../build-3.18.140-vee3
```

O padrão é `lineage_vee3_defconfig`. O comando exige uma saída vazia fora da
árvore de fontes, o alvo upstream no histórico ou no merge pendente, ausência
de conflitos e as seleções de hardware corretas após regenerar a configuração.
O log fica no diretório de saída. Sucesso da compilação continua separado da
validação em hardware.
