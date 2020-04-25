# Mamba
## A bytecode optimizer for Python

Mamba optimizes the bytecode in a given _pyc_ or _pyo_ file by applying both generic 
compiler optmization passes as well as optmization passes specific to the Python 
language itself.

Mamba is currently alpha level software and should not be used for production code. 

Below is a list of the optimization passes performed by Mamba. 
All examples use CPython 2.7.10 but should apply to CPython 3.

Please note that these optimization passes work together and are applied in several 
passes allowing each optimization to open the door for future optimizations.

## Generic Optimization Passes

### Constant Propagation

When a variable is assigned to a constant value, references to the variable can be 
replaced with references to the constant value instead. This helps enable further 
optimizations and can lead to a reduction of the bytecode size.

Example:

For the following Python snippet:

    a = 5
    b = a + 3

The following bytecode is generated:

    [0] LOAD_CONST (5)
    [3] STORE_NAME (a)
    [6] LOAD_NAME (a)
    [9] LOAD_CONST (3)
    [12] BINARY_ADD 
    [13] STORE_NAME (b)
	
After constant propagation, the bytecode is:

    [0] LOAD_CONST (5)
    [3] STORE_NAME (a)
    [6] LOAD_CONST (5)
    [9] LOAD_CONST (3)
    [12] BINARY_ADD 
    [13] STORE_NAME (b)

As you can see, BINARY\_ADD @ offset 12 now works with two constant values on 
the stack instead of one constant and one variable (and variable a is now unused).

Performance gains for this optimization:

    $ python -m timeit "a = 5" "b = a + 3"
    10000000 loops, best of 3: 0.0654 usec per loop
    
    $ python -m timeit "a = 5" "b = 5 + 3"
    10000000 loops, best of 3: 0.0474 usec per loop

### Constant Folding

If a constant expression is encountered it can be replaced with the result of the 
expression at compile time. This saves both runtime performance and leads to a 
reduction in bytecode size.

Example:

Building on the previous Python snippet:

    a = 5
    b = a + 3
    
The following bytecode is generated:

    [0] LOAD_CONST (5)
    [3] STORE_NAME (a)
    [6] LOAD_NAME (a)
    [9] LOAD_CONST (3)
    [12] BINARY_ADD 
    [13] STORE_NAME (b)
	
After constant propagation and constant folding, the bytecode is:

    [0] LOAD_CONST (5)
    [3] STORE_NAME (a)
    [6] LOAD_CONST (8)
    [9] STORE_NAME (b)
    
Here the expression 5 + 3 has been moved from runtime to compile time and replaced 
with the constant value of 8 in the bytecode. We now have two fewer opcodes and have 
saved 4 bytes.

Performance gains for this optimization:

    $ python -m timeit "a = 5" "b = a + 3"
    10000000 loops, best of 3: 0.0654 usec per loop

    $ python -m timeit "a = 5" "b = 8"
    10000000 loops, best of 3: 0.0477 usec per loop
    
### Unused Variable Removal

If a variable is set to a constant value and is not used, it can be removed from the 
byte code. This leads to a reduction in the bytecode size as well as fewer operations 
being executed at runtime.

Example:

Building on the previous Python snippet:

    a = 5
    b = a + 3
    
The following bytecode is generated:

    [0] LOAD_CONST (5)
    [3] STORE_NAME (a)
    [6] LOAD_NAME (a)
    [9] LOAD_CONST (3)
    [12] BINARY_ADD 
    [13] STORE_NAME (b)
	
After constant propagation, constant folding and unused variable removal, 
the bytecode is:

    # all bytecode has been removed!

Due to constant propagation and constant folding variables a and b can be safely 
removed from the bytecode. We now have 6 fewer operations and have saved 13 bytes.

Performance gains for this optimization:

    $ python -m timeit "a = 5" "b = a + 3"
    10000000 loops, best of 3: 0.0654 usec per loop

    $ python -m timeit ""
    10000000 loops, best of 3: 0.0129 usec per loop
    
### Constant If Collapsing

If an if statement clause consists of a constant value, the statement can be replaced 
with either the if or else body itself, depending on the constant value.

Example:

For the following Python snippet:

    LOG_LEVEL_NONE = 0
    LOG_LEVEL_DEBUG = 1
    LOG_LEVEL_ERROR = 2
    LOG_LEVEL = LOG_LEVEL_NONE

    if LOG_LEVEL:
        print "Some log statement: {} {} {}".format(1000, None, True)

The following bytecode is generated:

    [0] LOAD_CONST (0)
    [3] STORE_NAME (LOG_LEVEL_NONE)
    [6] LOAD_CONST (1)
    [9] STORE_NAME (LOG_LEVEL_DEBUG)
    [12] LOAD_CONST (2)
    [15] STORE_NAME (LOG_LEVEL_ERROR)
    [18] LOAD_NAME (LOG_LEVEL_NONE)
    [21] STORE_NAME (LOG_LEVEL)
    [24] LOAD_NAME (LOG_LEVEL)
    [27] POP_JUMP_IF_FALSE (53)
    [30] LOAD_CONST (Some log statement: {} {} {})
    [33] LOAD_ATTR (format)
    [36] LOAD_CONST (1000)
    [39] LOAD_CONST (None)
    [42] LOAD_NAME (True)
    [45] CALL_FUNCTION (None)
    [48] PRINT_ITEM
    [49] PRINT_NEWLINE
    [50] JUMP_FORWARD (0)
    
After all previous optimization passes have completed the value of LOG_LEVEL is now a 
constant literal (0) and can be used to deduce the value of the if statement at 
compile time. This results in the following bytecode:

    # all bytecode has been removed!
    
We have 19 less operations to execute and have saved 53 bytes.

Performance gains for this optimization:

    $ python -m timeit "LOG_LEVEL_NONE = 0" "LOG_LEVEL_DEBUG = 1" "LOG_LEVEL_ERROR = 2" "LOG_LEVEL = LOG_LEVEL_NONE" "if LOG_LEVEL:" "  print 'Some log statement: {} {} {}'.format(1000, None, True)"
    10000000 loops, best of 3: 0.0955 usec per loop
    
    $ python -m timeit ""
    10000000 loops, best of 3: 0.0129 usec per loop

## Function Inlining

In certain circumstances a call to a function can be replaced with the operations that 
function would have executed. This saves on the cost of a function call and can lead to 
further optimizations.

Example:

For the following Python snippet:

    def addFive(n):
        return n + 5
    
    a = 5
    b = addFive(a)
    
The following bytecode is generated:

    [0] LOAD_CONST (<code object addFive at 0x1060fddb0, file "demo.py", line 1>)
    [3] MAKE_FUNCTION (None)
    [6] STORE_NAME (addFive)
    [9] LOAD_CONST (5)
    [12] STORE_NAME (a)
    [15] LOAD_NAME (addFive)
    [18] LOAD_NAME (a)
    [21] CALL_FUNCTION (None)
    [24] STORE_NAME (b)
    
After function inlining, the bytecode becomes:

    [0] LOAD_CONST (<code object addFive at 0x106bf0db0, file "demo.py", line 1>)
    [3] MAKE_FUNCTION (None)
    [6] STORE_NAME (addFive)
    [9] LOAD_CONST (5)
    [12] LOAD_CONST (5)
    [15] BINARY_ADD
    [16] STORE_NAME (b)
    
Here the function addFive is no longer called. Instead the contents of the function have 
been moved into the call site. We have 2 fewer operations and have saved 6 bytes. 

Performance gains for this optimization:

    $ python -m timeit "def addFive(n):" "  return n + 5" "a = 5" "b = addFive(5)"
    1000000 loops, best of 3: 0.263 usec per loop
    
    $ python -m timeit "def addFive(n):" "  return n + 5" "b = 5 + 5"
    10000000 loops, best of 3: 0.097 usec per loop

Note that this also sets the bytecode up for further optimizations such as constant folding and 
unused variable removal, which produces the following bytecode:

    [0] LOAD_CONST (<code object addFive at 0x106933db0, file "demo.py", line 1>)
    [3] MAKE_FUNCTION (None)
    [6] STORE_NAME (addFive)
    [9] LOAD_CONST (10)
    
Performance gains for this optimization:

    $ python -m timeit "def addFive(n):" "  return n + 5" "a = 5" "b = addFive(5)"
    1000000 loops, best of 3: 0.263 usec per loop
    
    $ python -m timeit "def addFive(n):" "  return n + 5" "10"
    10000000 loops, best of 3: 0.0727 usec per loop

The function addFive can also be completely removed reducing the bytecode to:

    [0] LOAD_CONST (10)
    
Which is 24 bytes smaller than the snippet and saves 9 operations.

Performance gains for this optimization:

    $ python -m timeit "def addFive(n):" "  return n + 5" "a = 5" "b = addFive(5)"
    1000000 loops, best of 3: 0.263 usec per loop
    
    $ python -m timeit "10"
    100000000 loops, best of 3: 0.013 usec per loop

## Python Specific Optimization Passes

### _bool(const)_ conversion to _not not const_

In Python bool(const) is noticably slower than not not const. This is largely due to 
the cost of a function call. When appropriate converting to not not const can show 
significant improvements.

Example:

For the following Python snippet:

    a = 5
    b = bool(a)
    
The following bytecode is generated:

    [0] LOAD_CONST (5)
    [3] STORE_NAME (a)
    [6] LOAD_NAME (bool)
    [9] LOAD_NAME (a)
    [12] CALL_FUNCTION (None)
    [15] STORE_NAME (b)
    
Constant propagation of a and converting bool(5) to not not 5 results in the 
following bytecode which has 2 less operations and saves 10 bytes:

    [0] LOAD_CONST (5)
    [3] UNARY_NOT
    [4] UNARY_NOT
    [5] STORE_NAME (b)
    
Performance gains for this optimization:

    $ python -m timeit "a = 5" "b = bool(a)"
    10000000 loops, best of 3: 0.173 usec per loop
    
    $ python -m timeit "b = not not 5"
    10000000 loops, best of 3: 0.0465 usec per loop
    
Also note that not not const is subject to constant folding and propagation itself.

Example:

For the following Python snippet:

    bool(5)
    
The following bytecode is generated:

    [0] LOAD_NAME (bool)
    [3] LOAD_CONST (5)
    [6] CALL_FUNCTION (None)
    
After translating to not not 5 and constant folding the bytecode is optimized to:

    [0] LOAD_CONST (True)
    
Which removes an additional 2 operations and saves another 4 bytes.

Performance gains after converting to not not and folding:

    $ python -m timeit "bool(5)"
    10000000 loops, best of 3: 0.148 usec per loop

    $ python -m timeit "True"
    10000000 loops, best of 3: 0.033 usec per loop