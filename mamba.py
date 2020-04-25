import marshal
import opcode
import operator
import types

class MutableByteCode():
    def __init__(self, code):
        self.bytes = bytearray(code.co_code)
        self.consts = list(code.co_consts)
        self.names = list(code.co_names)

def opargAtIndex(bytes, i):
    return bytes[i] + (bytes[i + 1] << 8)

def setConstOpargAtIndex(byteCode, index, value):
    newOparg = len(byteCode.consts)
    byteCode.consts.append(value)
    byteCode.bytes[index] = newOparg & 0xFF
    byteCode.bytes[index + 1] = (newOparg >> 8) & 0xFF

def nextOp(bytes, i):
    op = bytes[i]
    opname = opcode.opname[op]
    oparg = None
    bytesConsumed = 1

    if op >= opcode.HAVE_ARGUMENT:
        oparg = opargAtIndex(bytes, i + 1)
        bytesConsumed = 3

    return (op, opname, oparg, bytesConsumed)

def opsInBytes(bytes):
    ops = []
    i = 0
    l = len(bytes)

    while i < l:
        (op, opname, oparg, bytesConsumed) = nextOp(bytes, i)
        ops.append(op)
        i += bytesConsumed

    return ops

def countOpCodes(byteCode):
    """ Reports the number of opcodes in the given bytecode.

    Note the number of opcodes does not always equal the number of 
    bytes since opcodes can have a two byte argument.
    """

    bytes = byteCode.bytes
    l = len(bytes)
    i = 0
    count = 0

    while i < l:
        (op, opname, oparg, bytesConsumed) = nextOp(bytes, i)
        i += bytesConsumed
        count += 1

    print "Found {0} opcodes".format(count)

def findConstantLiterals(byteCode):
    """ Finds all declarations of constant literals.

    Returns a dictionary of {varName: byteIndex}
    """

    bytes = byteCode.bytes
    l = len(bytes)
    i = 0
    constLiterals = {}

    loadConstOp = opcode.opmap['LOAD_CONST']
    storeNameOp = opcode.opmap['STORE_NAME']

    while i < l:
        (op, opname, oparg, bytesConsumed) = nextOp(bytes, i)

        if op == loadConstOp and not isinstance(byteCode.consts[oparg], types.CodeType):
            (op2, opname2, oparg2, bytesConsumed2) = nextOp(bytes, i + bytesConsumed)

            if op2 == storeNameOp:
                varName = byteCode.names[oparg2]
                constLiterals[varName] = i
                bytesConsumed += bytesConsumed2

        i += bytesConsumed

    return constLiterals

def findFunctionDeclarations(byteCode):
    """Finds all function declarations in the given bytecode.
    """

    bytes = byteCode.bytes
    l = len(bytes) - 9
    i = 0
    decls = {}

    loadConstOp = opcode.opmap['LOAD_CONST']
    makeFunctionOp = opcode.opmap['MAKE_FUNCTION']
    storeNameOp = opcode.opmap['STORE_NAME']

    while i < l:
        if bytes[i] == loadConstOp and bytes[i + 3] == makeFunctionOp and bytes[i + 6] == storeNameOp:
            funcName = byteCode.names[opargAtIndex(bytes, i + 7)]
            decls[funcName] = i
        i += 1

    return decls

def performConstantPropagation(byteCode):
    """ Replaces LOAD_NAME with LOAD_CONST for constant literal variables

    Scans for LOAD_NAME and replaces it with LOAD_CONST if the variable 
    name being loaded was previous detected as:

    LOAD_CONST 
    STORE_NAME

    LOAD_NAME and LOAD_CONST both occupy 3 bytes.

    todo: this is too agressive, breaks:

    i = 0
    while i < 10:
    """

    bytes = byteCode.bytes
    l = len(bytes)
    i = 0
    modifications = 0
    constLiterals = findConstantLiterals(byteCode)

    loadConstOp = opcode.opmap['LOAD_CONST']
    loadNameOp = opcode.opmap['LOAD_NAME']

    while i < l:
        (op, opname, oparg, bytesConsumed) = nextOp(bytes, i)

        if op == loadNameOp:
            varName = byteCode.names[oparg]
            if varName in constLiterals:
                valueIndex = constLiterals[varName]
                bytes[i] = loadConstOp
                bytes[i + 1] = bytes[valueIndex + 1];
                bytes[i + 2] = bytes[valueIndex + 2];

                print "** Propagated {} as constant literal @ byte {}".format(varName, i)
                modifications += 1

        i += bytesConsumed

    return modifications

def performConstantFolding(byteCode):
    """Replaces operations such as 5 + 7 with 12 at compile time.

    Here we are looking for a LOAD_CONST LOAD_CONST _SAFE_OP_
    Where _SAFE_OP_ is one of:

    BINARY_ADD
    BINARY_SUBTRACT

    Or LOAD_CONST _SAFE_OP_
    Where _SAFE_OP_ is one of:
    UNARY_NOT

    todo: special case LOAD_CONST UNARY_NOT UNARY_NOT to prevent a pass
    todo: check if foldedValue is already in byteCode.consts and reuse index
    """
    
    bytes = byteCode.bytes
    l = len(bytes)
    i = 3
    modifications = 0

    loadConstOp = opcode.opmap['LOAD_CONST']
    unaryNotOp = opcode.opmap['UNARY_NOT']
    nopOp = opcode.opmap['NOP']

    foldableOps = { 
        opcode.opmap['BINARY_ADD'] : ('+', operator.add), 
        opcode.opmap['BINARY_SUBTRACT'] : ('-', operator.sub),
        }

    while i < l:
        if i > 5 and bytes[i] in foldableOps and bytes[i - 3] == loadConstOp and bytes[i - 6] == loadConstOp:
            value1 = byteCode.consts[opargAtIndex(bytes, i - 5)]
            value2 = byteCode.consts[opargAtIndex(bytes, i - 2)]

            if not isinstance(value1, types.CodeType) and not isinstance(value2, types.CodeType):
                token, func = foldableOps[bytes[i]]
                foldedValue = func(value1, value2)
                setConstOpargAtIndex(byteCode, i - 5, foldedValue)
                for byteIndex in range(i - 3, i + 1):
                    bytes[byteIndex] = nopOp

                print "** Folded {} {} {} to {} @ byte {}".format(value1, token, value2, foldedValue, i)
                modifications += 1

        elif bytes[i] == unaryNotOp and bytes[i - 3] == loadConstOp:
            constValue = byteCode.consts[opargAtIndex(bytes, i - 2)]

            if not isinstance(constValue, types.CodeType):
                foldedValue = not constValue
                setConstOpargAtIndex(byteCode, i - 2, foldedValue)
                bytes[i] = nopOp
                print "** Folded not {} to {} @ byte {}".format(constValue, foldedValue, i)
                modifications += 1

        i += 1

    return modifications

def removeUnusedVariables(byteCode):
    """Detects variables that are not referenced after their declaration and removes them.
    
    Curently only variables that are set to constant literal values are supported.

    Variable declarations are replaced with 6 NOPs (3 for LOAD_CONST and 3 for STORE_NAME).
    """

    bytes = byteCode.bytes
    l = len(bytes)
    i = 0
    modifications = 0
    constLiterals = findConstantLiterals(byteCode)

    loadNameOp = opcode.opmap['LOAD_NAME']
    nopOp = opcode.opmap['NOP']

    while i < l:
        (op, opname, oparg, bytesConsumed) = nextOp(bytes, i)

        if op == loadNameOp:
            varName = byteCode.names[oparg]
            if varName in constLiterals:
                del constLiterals[varName]

        i += bytesConsumed

    for varName, byteIndex in constLiterals.iteritems():
        for i in range(byteIndex, byteIndex + 6):
            bytes[i] = nopOp

        print "** Removed unused var {} @ byte {}".format(varName, byteIndex + 3)
        modifications += 1

    return modifications

def collapseConstantIfs(byteCode):
    """Detects constant if expressions and inlines the appropriate body
    """

    bytes = byteCode.bytes
    l = len(bytes)
    i = 0
    modifications = 0

    loadConstOp = opcode.opmap['LOAD_CONST']
    jumpIfFalseOp = opcode.opmap['POP_JUMP_IF_FALSE']
    jumpForwardOp = opcode.opmap['JUMP_FORWARD']
    nopOp = opcode.opmap['NOP']

    while i < l:
        (op, opname, oparg, bytesConsumed) = nextOp(bytes, i)

        if op == loadConstOp and not isinstance(byteCode.consts[oparg], types.CodeType):
            constValue = byteCode.consts[oparg]
            (op2, opname2, oparg2, bytesConsumed2) = nextOp(bytes, i + bytesConsumed)

            if op2 == jumpIfFalseOp:
                bytesConsumed += bytesConsumed2
                if not constValue:
                    for index in range(i, oparg2):
                        bytes[index] = nopOp
                else:
                    for index in range(i, i + 6):
                        bytes[index] = nopOp

                    for index in range(i + 6, l):
                        if bytes[index] == jumpForwardOp:
                            (op3, opname3, oparg3, bytesConsumed3) = nextOp(bytes, index)
                            bytesConsumed += bytesConsumed3
                            for index2 in range(index, index + bytesConsumed3 + oparg3):
                                bytes[index2] = nopOp
                            break

                print "** Collapsed constant if statement @ byte " + str(i + 3)
                modifications += 1

        i += bytesConsumed

    return modifications

def inlineFunctions(byteCode):
    """Inlines functions which are deemed pure and within an acceptable bytecode size.

    Ideal candidates for inlining are those that will result in further constant 
    propagation and folding. Currently only functions called with constant values are 
    considered, however this is not completely necessary.

    todo: be smarter about finding nops to overwrite
    todo: expand scope of this optimization since Python function calls are expensive.
    """

    bytes = byteCode.bytes
    l = len(bytes)
    i = 9
    modifications = 0

    loadNameOp = opcode.opmap['LOAD_NAME']
    loadConstOp = opcode.opmap['LOAD_CONST']
    callFunctionOp = opcode.opmap['CALL_FUNCTION']
    nopOp = opcode.opmap['NOP']

    inlineWhitelist = set((opcode.opmap['LOAD_FAST'], 
                          opcode.opmap['LOAD_CONST'], 
                          opcode.opmap['BINARY_ADD'], 
                          opcode.opmap['RETURN_VALUE']))

    inlineMaxOps = 10

    while i < l:
        if bytes[i] == callFunctionOp and bytes[i - 3] == loadConstOp and bytes[i - 6] == loadNameOp:
            funcNameOparg = opargAtIndex(bytes, i - 5)
            funcName = byteCode.names[funcNameOparg]
            func = None
            
            for index in range(0, len(byteCode.consts)):
                if isinstance(byteCode.consts[index], types.CodeType):
                    if byteCode.consts[index].co_name == funcName:
                        func = byteCode.consts[index]
                        break

            if func is not None:
                bytesToInline = bytearray(func.co_code)
                opsToInline = opsInBytes(bytesToInline)

                inlineOpsLen = len(opsToInline)
                if inlineOpsLen >= inlineMaxOps:
                    continue

                canInline = True
                for op in opsToInline:
                    if op not in inlineWhitelist:
                        canInline = False
                        break

                if not canInline:
                    continue

                bytes[i - 6] = nopOp
                bytes[i - 5] = nopOp
                bytes[i - 4] = nopOp

                bytes[i] = nopOp
                bytes[i + 1] = nopOp
                bytes[i + 2] = nopOp

                bytes[i:i] = bytesToInline[3:len(bytesToInline) - 1]
                funcConstValue = func.co_consts[opargAtIndex(bytes, i + 1)]
                setConstOpargAtIndex(byteCode, i + 1, funcConstValue)

                print "** Inlined call to function {} @ byte {}".format(funcName, i)
                modifications += 1

        i += 1

    return modifications

def removeUnusedFunctions(byteCode):
    """Removes functions that are not used.
    """

    bytes = byteCode.bytes
    l = len(bytes)
    i = 0
    modifications = 0
    decls = findFunctionDeclarations(byteCode)

    loadNameOp = opcode.opmap['LOAD_NAME']
    nopOp = opcode.opmap['NOP']

    while i < l:
        (op, opname, oparg, bytesConsumed) = nextOp(bytes, i)

        if op == loadNameOp:
            name = byteCode.names[oparg]
            if name in decls:
                del decls[name]

        i += bytesConsumed

    for name, byteIndex in decls.iteritems():
        for byteToClear in range(byteIndex, byteIndex + 9):
            bytes[byteToClear] = nopOp
        print "** Removed unused function {} @ byte {}".format(name, byteIndex)
        modifications += 1

    return modifications

def translateBoolToNotNot(byteCode):
    """Translates bool(const) to not not const

    Perhaps due largely to function call overhead, bool(const) is significantly 
    slower than not not const
    """

    bytes = byteCode.bytes
    l = len(bytes)
    i = 6
    modifications = 0

    callFunctionOp = opcode.opmap['CALL_FUNCTION']
    loadConstOp = opcode.opmap['LOAD_CONST']
    loadNameOp = opcode.opmap['LOAD_NAME']
    unaryNotOp = opcode.opmap['UNARY_NOT']
    nopOp = opcode.opmap['NOP']

    while i < l:
        if bytes[i] == callFunctionOp and bytes[i - 3] == loadConstOp and bytes[i - 6] == loadNameOp:
            oparg1 = opargAtIndex(bytes, i - 2)
            oparg2 = opargAtIndex(bytes, i - 5)

            if not isinstance(oparg1, types.CodeType) and code.co_names[oparg2] == 'bool':
                bytes[i - 6] = bytes[i - 3]
                bytes[i - 5] = bytes[i - 2]
                bytes[i - 4] = bytes[i - 1]
                bytes[i - 3] = unaryNotOp
                bytes[i - 2] = unaryNotOp
                for nopIndex in range(i - 1, i + 3):
                    bytes[nopIndex] = nopOp

                constValue = byteCode.consts[oparg1]
                print "** Replaced bool({}) with not not {} @ byte {}".format(constValue, constValue, i)

                modifications += 1
                i += 2

        i += 1

    return modifications

def removeNops(byteCode):
    """Remove all NOPs from the given bytecode.

    Optimization passes that replace instructions with instructions that 
    fill fewer bytes than previously occupied will fill the remaining space 
    with NOPs. This step cannot be a simple filter where byte[i] != NOP 
    since any op arg byte set to NOP will be removed.
    """

    bytes = byteCode.bytes
    l = len(bytes)
    i = 0
    filteredBytes = bytearray()

    nopOp = opcode.opmap['NOP']
    nopsRemoved = 0

    while i < l:
        op = bytes[i]
        bytesConsumed = 1
        if op != nopOp:
            filteredBytes.append(op)
            if op >= opcode.HAVE_ARGUMENT:
                filteredBytes.append(bytes[i + 1])
                filteredBytes.append(bytes[i + 2])
                bytesConsumed += 2
        else:
            nopsRemoved += 1

        i += bytesConsumed

    if nopsRemoved > 0:
        print "** Removed {} NOPs".format(nopsRemoved)

    byteCode.bytes = filteredBytes
    return nopsRemoved

def printCode(byteCode):
    bytes = byteCode.bytes
    l = len(bytes)
    i = 0

    while i < l:
        (op, opname, oparg, bytesConsumed) = nextOp(bytes, i)
        desc = None

        if op >= opcode.HAVE_ARGUMENT:
            if op in opcode.hasconst:
                desc = byteCode.consts[oparg]
                #if isinstance(constCode, types.CodeType):
                #    printCode(constCode)
            elif op in opcode.hasname:
                desc = byteCode.names[oparg]
            #elif op in opcode.haslocal:
            #    print "haslocal"
            #elif op in opcode.hascompare:
            #    print "hascompare"
            #elif op in opcode.hasfree:
            #    print "hasfree"
            elif op in opcode.hasjrel:
                desc = oparg
            elif op in opcode.hasjabs:
                desc = oparg

        if op >= opcode.HAVE_ARGUMENT:
            print "[{}] {} ({})".format(i, opname, desc)
        else:
            print "[{}] {}".format(i, opname)

        i += bytesConsumed


try:
    f = open("demo.pyc", "rb")
    _ = f.read(8)
    code = marshal.load(f)
finally:
    f.close()

byteCode = MutableByteCode(code)

preBytesLen = len(byteCode.bytes)

print "Original bytecode:\n"

printCode(byteCode)
countOpCodes(byteCode)

passes = 0

while passes < 100:
    print "\nPass {}:".format(passes + 1)

    modifications = 0

    # generic compiler optimizations
    modifications += performConstantPropagation(byteCode)
    modifications += performConstantFolding(byteCode)
    modifications += collapseConstantIfs(byteCode)
    modifications += removeUnusedVariables(byteCode)
    modifications += inlineFunctions(byteCode)
    modifications += removeUnusedFunctions(byteCode)
    
    # python specific optimizations
    modifications += translateBoolToNotNot(byteCode)

    # remove nop placeholders
    modifications += removeNops(byteCode)

    if modifications == 0:
        print "No modifications made"
        print "Bytecode has been optimized\n"
        break

    passes += 1

if passes == 100:
    print "Stopped optimizing due to 100 passes\n"

# todo: clean up co_consts, etc

print "Optimized bytecode:\n"

printCode(byteCode)
countOpCodes(byteCode)

postBytesLen = len(byteCode.bytes)

print "Went from {} to {} bytes".format(preBytesLen, postBytesLen)

