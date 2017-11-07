#!/usr/bin/env python3

# Copyright 2017 Patrick O. Perry.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import math
import re

try:
    import unicode_data
except ModuleNotFoundError:
    from util import unicode_data


EXCLUSIONS = 'data/ucd/CompositionExclusions.txt'

# get the length-2 decomposition maps (excluding hangul and compatibility maps)

decomp_map = {}
starter = [None] * len(unicode_data.uchars)

for code in range(len(unicode_data.uchars)):
    u = unicode_data.uchars[code]
    if u is None:
        continue

    ccc = u.ccc
    if ccc is None or ccc == 0:
        starter[code] = True
    else:
        starter[code] = False

    d = u.decomp
    if d is not None and d.type is None:
        if len(d.map) == 2:
            decomp_map[code] = tuple(d.map)


# exclude non-starter decomposiitons

decomp_map2 = {}
for p,d in decomp_map.items():
    if starter[p] and starter[d[0]]:
        decomp_map2[p] = d
decomp_map = decomp_map2


# exclude composition exclusions

try:
    file = open(EXCLUSIONS, 'r')
except FileNotFoundError:
    file = open('../' + EXCLUSIONS, 'r')

with file:
    for line in file:
        fields = line.partition('#')
        code = fields[0].strip()
        if len(code) > 0:
            code = int(code, 16)
            if code in decomp_map:
                del decomp_map[code]

#print('primary\tletter\tcode')
#for p,d in decomp_map.items():
#    print(p, '\t', d[0], '\t', d[1], sep='')

# construct table l : [(c,p)]
compose_map = {}
for p,d in decomp_map.items():
    l = d[0]
    c = d[1]
    if l not in compose_map:
        compose_map[l] = []
    compose_map[l].append((c, p))

compose = []
combiner = []
primary = []
off = 0
for code in range(len(unicode_data.uchars)):
    if code in compose_map:
        maps = compose_map[code]
        maps.sort()
        compose.append((off, len(maps)))
        combiner.extend([c for (c,p) in maps])
        primary.extend([p for (c,p) in maps])
        off += len(maps)
    else:
        compose.append((0,0))

# Hangul
hangul_lpart = off
hangul_lvpart = off + 1

for code in range(0x1100, 0x1113):
    compose[code] = (hangul_lpart, 1)

for code in range(0xAC00, 0xD7A4):
    if (code - 0xAC00) % 28 == 0:
        compose[code] = (hangul_lvpart, 1)


def compute_tables(block_size):
    nblock = len(compose) // block_size
    stage1 = [None] * nblock
    stage2 = []
    stage2_dict = {}
    for i in range(nblock):
        begin = i * block_size
        end = begin + block_size
        block = tuple(compose[begin:end])
        if block in stage2_dict:
            j = stage2_dict[block]
        else:
            j = len(stage2)
            stage2_dict[block] = j
            stage2.append(block)
        stage1[i] = j
    return (stage1,stage2)


def stage1_item_size(nstage2):
    nbyte = math.ceil(math.log(nstage2, 2) / 8)
    size = 2**math.ceil(math.log(nbyte, 2))
    return size

page_size = 4096
block_size = 256

nbytes = {}

best_block_size = 1
smallest_size = len(compose)

for i in range(1,17):
    block_size = 2**i
    stage1,stage2 = compute_tables(block_size)

    nbyte1 = len(stage1) * stage1_item_size(len(stage2))
    nbyte2 = len(stage2) * block_size

    nbyte1 = math.ceil(nbyte1 / page_size) * page_size
    nbyte2 = math.ceil(nbyte2 / page_size) * page_size
    nbyte = nbyte1 + nbyte2
    nbytes[block_size] = nbyte

    if nbyte < smallest_size:
        smallest_size = nbyte
        best_block_size = block_size


block_size = best_block_size
stage1,stage2 = compute_tables(block_size)

type1_size = stage1_item_size(len(stage2))
if type1_size == 1:
    type1 = 'uint8_t'
elif type1_size == 2:
    type1 = 'uint16_t'
elif type1_size == 4:
    type1 = 'uint32_t'
else:
    type1 = 'uint64_t'

type2 = 'struct composition'


# Write compose.h to stdout


print("/* This file is automatically generated. DO NOT EDIT!")
print("   Instead, edit gen-compose.py and re-run. */")
print("")
print("/*")
print(" * Unicode primary composites.")
print(" *")
print(" * Defined in Unicode Sec 3.11 \"Normalization Forms\"")
print(" *")
print(" * We use the two-stage lookup strategy described at")
print(" *")
print(" *     http://www.strchr.com/multi-stage_tables")
print(" *")
print(" */")
print("")
print("#ifndef UNICODE_COMPOSE_H")
print("#define UNICODE_COMPOSE_H")
print("")
print("#include <stdint.h>")
print("")
print("/* composition")
print(" * -----------")
print(" * offset: the offset into the primary and combiner arrays,")
print(" *         or 0 if there are no compositions")
print(" * length: the number of compositions for the codepont")
print(" */")
print("struct composition {")
print("\tunsigned offset : 11;")
print("\tunsigned length : 5;")
print("};")
print("")
print("#define COMPOSITION_BLOCK_SIZE", block_size)
print("")
print("#define COMPOSITION_HANGUL_LPART", hangul_lpart)
print("")
print("#define COMPOSITION_HANGUL_LVPART", hangul_lvpart)
print("")
print("static const " + type1 + " composition_stage1[] = {")
for i in range(len(stage1) - 1):
    if i % 16  == 0:
        print("/* U+{:04X} */".format(i * block_size), end="")
    print("{0: >3},".format(stage1[i]), end="")
    if i % 16 == 15:
        print("")
print("{0: >3}".format(stage1[len(stage1) - 1]))
print("};")
print("")
print("static const " + type2 + " composition_stage2[][" +
        str(block_size) + "] = {")
for i in range(len(stage2)):
    print("  /* block " + str(i) + " */")
    print("  {", end="")
    for j in range(block_size):
        print("{{{0: >3}".format(stage2[i][j][0]), end="")
        print(",{0: >2}}}".format(stage2[i][j][1]), end="")
        if j + 1 == block_size:
            print("\n  }", end="")
        else:
            print(",", end="")
            if j % 7 == 6:
                print("\n   ", end="")
            else:
                print(" ", end="")
    if i + 1 != len(stage2):
        print(",\n")
    else:
        print("")
print("};")
print("")
print("static const int32_t composition_combiner[] = {")
for i in range(len(combiner) - 1):
    if i % 8  == 0:
        print("/* {0: >3} */ ".format(i), end="")
    print("0x{0:04X},".format(combiner[i]), end="")
    if i % 8 == 7:
        print("")
print("0x{0:04X}".format(combiner[len(combiner) - 1]))
print("};")
print("")
print("static const int32_t composition_primary[] = {")
for i in range(len(primary) - 1):
    if i % 8  == 0:
        print("/* {0: >3} */ ".format(i), end="")
    print("0x{0:04X},".format(primary[i]), end="")
    if i % 8 == 7:
        print("")
print("0x{0:04X}".format(primary[len(primary) - 1]))
print("};")
print("")
print("#endif /* UNICODE_COMPOSE_H */")
