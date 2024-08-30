import re

# perform the local value numbering optimization
def LVN(program):

    # returns 3 items:
    
    # 1. a new program (list of classier instructions)
    # with the LVN optimization applied

    # 2. a list of new variables required (e.g. numbered virtual
    # registers and program variables)

    # 3. a number with how many instructions were replaced

    # We will follow the suggested path

    # 1. Splitting the code into basic blocks:
    # To do this we will follow the algorithm in the slides that iterates over the 3 address instructions
    # and if we see a branch or a label we finalize the current basic block and start a new one

    # First we need to parse the program list to be able to identify branch and label instructions

    # To parse instructions we use regular expressions and follow the format of the example in the assignment
    # We need to be careful in the ordering because of the prefixes, for example is we placed the assignment instruction at the beginning we would get errors
    instruction_types = [
        (r"(?P<label>\S+):", ["label"]),  # labels
        (r"(?P<dst>\S+)=(?P<instr>\S+)\((?P<op1>\S+),(?P<op2>\S+)\);", ["dst", "instr", "op1", "op2"]),  # binary operations (add, sub, mult, div, eq, lt for ints or floats)
        (r"(?P<instr>\S+)\((?P<op1>\S+),(?P<op2>\S+),(?P<op3>\S+)\);", ["instr", "op1", "op2", "op3"]),  # bne or beq
        (r"(?P<dst>\S+)=(?P<instr>\S+)\((?P<op1>\S+)\);", ["dst", "instr", "op1"]),  # unary operation (int2vr, float2vr, vr2int, vr2float, vr_int2float, vr_float2int)
        (r"(?P<assigned>\S+)=(?P<op1>\S+);", ["assigned", "op1"]),  # assignment
        (r"(?P<instr>\S+)\((?P<op1>\S+)\);", ["instr", "op1"])  # unconditional branch
    ]

    program_parsed = []
    for instruction in program:
        instruction = "".join(instruction.split()) # we remove white spaces
        for type in instruction_types:
            regExp, groupNames = type
            match = re.match(regExp, instruction)
            if match is not None:
                # each parsed instruction will be a dictionary
                program_parsed.append({name: match.group(name) for name in groupNames})
                break  # stop checking further patterns if a match is found

    # Now we are ready to use the splitting algorithm
    basic_blocks = []
    bb = []
    for i in range(len(program)):
        instruction = program[i]
        parsed_instruction = program_parsed[i]
        # If the instruction is a branch, add it to current block and start new block
        if parsed_instruction.get("instr") in ["branch", "beq", "bne"]:
            bb.append(instruction)
            basic_blocks.append(bb)
            bb = []
        # If the instruction has a label, start a new block with the label instruction
        elif parsed_instruction.get("label") is not None:
            if bb: # Ensure the current block is not empty before adding it
                basic_blocks.append(bb)
            bb = [instruction]
        # If it is a regular instruction we add it to the current block
        else:
            bb.append(instruction)
    # Append the last block if it is not empty
    if bb:
        basic_blocks.append(bb)

    # 2. Numbering
    new_variables = []
    num_replaced_instr = 0
    final_program = []
    for block in basic_blocks:
        # We will implement the local value numbering algorithm shown in the slides

        numbering_counter = 0 # To number all variables
        current_val = {} # A hash table to keep the current variable number for each variable
        H = {} # Our main hash table of the rhs mapped to their lhs
        block_length = len(block) # Before any patching
        patch_beginning = [] # A list where we add the assignments of the first numbered variables e.g. a0 = a
        patch_end = set() # We keep the lhs variables in this set because these are the modified variables and at the end we will have to assign original variables their latest values e.g. a = a0
        
        def add_new_variable(name, counter):
            variable_name = f"{name}_{counter}"
            if variable_name not in new_variables:
                new_variables.append(variable_name)
            return variable_name

        def add_patch(name, counter):
            patch = f"{name}_{counter} = {name};"
            patch_beginning.append(patch)
            return patch

        # We analyze each instruction of this basic block
        for i in range(len(block)):
            instruction = block[i]
            parsed_instruction = program_parsed[i]
            instr = parsed_instruction.get("instr")
            op1 = parsed_instruction.get("op1")
            op2 = parsed_instruction.get("op2")
            dst = parsed_instruction.get("dst")

            if instr in ["vr_float2int", "vr_int2float"]:
                numbering_arg1 = current_val.get(op1)
                # We number the source operand giving it a new number if it doesn't have any
                if numbering_arg1 is None:
                    numbering_arg1 = numbering_counter
                    current_val[op1] = numbering_counter
                    # Since this variable didn't have a number it could not be in new variables list yet (this is a list for all blocks so it can also be here because of another block)
                    add_new_variable(op1, numbering_counter)
                    # Since this is a rhs operand and we are numbering it for the first time we need to add it to the begginning patch
                    add_patch(op1, numbering_counter)
                    # We update the counter
                    numbering_counter += 1
                # The destination operand must always get a new number
                variable_name_dst = f"{dst}_{numbering_counter}"
                # We create the new code with the numbered registers
                block[i] = f"{variable_name_dst} = {instr}({op1}_{current_val[op1]});"
                # Since we numbered we need to check if it is a new variable and add it if it is
                add_new_variable(dst, numbering_counter)
                # For the lhs arguments we might also need to add them to the end patching (we will later check if this is the lastest value of the variable)
                patch_end.add(dst)
                current_val[dst] = numbering_counter
                numbering_counter += 1

            elif instr in ["vr2int", "vr2float"]:
                # We don't number IO variables
                # To assign a value to an IO variable it must always come from a register that must have already been declared (and therefore numbered) previously
                block[i] = f"{dst} = {instr}({op1}_{current_val[op1]});"

            elif instr in ["int2vr", "float2vr"]:
                # We don't need to take care of the op1: it's a number or IO variable
                # The destination operand must always get a new number
                block[i] = f"{dst}_{numbering_counter} = {instr}({op1});"
                add_new_variable(dst, numbering_counter)
                patch_end.add(dst)
                current_val[dst] = numbering_counter
                numbering_counter += 1

            elif parsed_instruction.get("assigned") is not None:
                assigned = parsed_instruction.get("assigned")
                # We number the source operand giving it a new number if it doesn't have any
                numbering_arg1 = current_val.get(op1)
                if numbering_arg1 is None:
                    numbering_arg1 = numbering_counter
                    current_val[op1] = numbering_counter
                    add_new_variable(op1, numbering_counter)
                    add_patch(op1, numbering_counter)
                    numbering_counter += 1
                # The destination operand must always get a new number
                block[i] = f"{assigned}_{numbering_counter} = {op1}_{numbering_arg1};"
                add_new_variable(assigned, numbering_counter)
                patch_end.add(assigned)
                current_val[assigned] = numbering_counter
                numbering_counter += 1

            elif instr in ["addi", "addf", "multi", "multf", "subi", "subf", "divi", "divf", "lti", "ltf", "eqi", "eqf"]:
                # We number the sources operand giving it a new number if it doesn't have any
                numbering_arg1 = current_val.get(op1)
                if numbering_arg1 is None:
                    numbering_arg1 = numbering_counter
                    current_val[op1] = numbering_counter
                    add_new_variable(op1, numbering_arg1)
                    add_patch(op1, numbering_arg1)
                    numbering_counter += 1

                numbering_arg2 = current_val.get(op2)
                if numbering_arg2 is None:
                    numbering_arg2 = numbering_counter
                    current_val[op2] = numbering_counter
                    add_new_variable(op2, numbering_arg2)
                    add_patch(op2, numbering_arg2)
                    numbering_counter += 1
                
                # The destination operand must always get a new number
                numbering_dst = numbering_counter
                current_val[dst] = numbering_counter
                numbering_counter += 1

                block[i] = f"{dst}_{numbering_dst} = {instr}({op1}_{numbering_arg1},{op2}_{numbering_arg2});"
                add_new_variable(dst, numbering_dst)
                patch_end.add(dst)

                # 4. Optimizing

                # We assume commutativity of integer addition, multiplication and equality
                # We save it in lexicographical order
                if instr in ["addi", "addf", "multi", "multf", "eqi", "eqf"] and op2 < op1:
                    key = f"{instr}({op2}_{numbering_arg2},{op1}_{numbering_arg1});"
                else:
                    key = f"{instr}({op1}_{numbering_arg1},{op2}_{numbering_arg2});"

                # We check if we can optimize the current instruction by copying a value instead of computing an arithmetic operation
                if key in H: # Yes! This operation has already been assigned to a register that we can copy
                    block[i] = f"{dst}_{numbering_dst} = {H[key]};"
                    num_replaced_instr += 1
                else: # No, we have to add ourselves as the first register with this operation
                    H[key] = f"{dst}_{numbering_dst}"

        # 3. Patching 
        # We pay special attention where we add the new code, especially if our basic block starts with a label or ends with a branch
        # Apply beginning patch to block
        if program_parsed[0].get("label") is not None:
            if block_length > 1:
                block = [block[0]] + patch_beginning + block[1:]
            else:
                block = [block[0]] + patch_beginning
        else:
            block = patch_beginning + block

        # Apply end patch to block
        if instr in ["branch", "beq", "bne", "blt", "bgt", "ble", "bge"]:
            for variable in patch_end:
                block.insert(len(block)-1, f"{variable} = {variable}_{current_val[variable]};")
        else:
            for variable in patch_end:
                block.append(f"{variable} = {variable}_{current_val[variable]};")

        # We prepare to start with the next block    
        final_program.append(block)
        program_parsed = program_parsed[block_length:]

    # Finally we prepare the optimized program and return the three requirements
    final_program_instructions = []
    for block in final_program:
        for instruction in block:
            final_program_instructions.append(instruction)

    return final_program_instructions, new_variables, num_replaced_instr



