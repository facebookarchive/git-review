#!/usr/bin/python -tt
#
# Copyright 2009-2010 Facebook, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
import re

class TokenizationError(Exception):
    pass


class PartialTokenError(TokenizationError):
    def __init__(self, token, msg):
        TokenizationError.__init__(self, msg)
        self.token = token
        self.error = msg


class State(object):
    def handleChar(self, tokenizer, char):
        raise NotImplementedError()

    def handleEnd(self, tokenizer):
        raise NotImplementedError()


class EscapeState(State):
    def handleChar(self, tokenizer, char):
        tokenizer.addToToken(char)
        tokenizer.popState()

    def handleEnd(self, tokenizer):
        # XXX: We could treat this as an indication to continue on to the next
        # line.
        msg = 'unterminated escape sequence'
        raise PartialTokenError(tokenizer.getPartialToken(), msg)


class QuoteState(State):
    def __init__(self, quote_char, escape_chars = '\\'):
        State.__init__(self)
        self.quote = quote_char
        self.escapeChars = escape_chars

    def handleChar(self, tokenizer, char):
        if char == self.quote:
            tokenizer.popState()
        elif char in self.escapeChars:
            tokenizer.pushState(EscapeState())
        else:
            tokenizer.addToToken(char)

    def handleEnd(self, tokenizer):
        msg = 'unterminated quote'
        raise PartialTokenError(tokenizer.getPartialToken(), msg)


class NormalState(State):
    def __init__(self):
        State.__init__(self)
        self.quoteChars = '"\''
        self.escapeChars = '\\'
        self.delimChars = ' \t\n'

    def handleChar(self, tokenizer, char):
        if char in self.escapeChars:
            tokenizer.pushState(EscapeState())
        elif char in self.quoteChars:
            tokenizer.addToToken('')
            tokenizer.pushState(QuoteState(char, self.escapeChars))
        elif char in self.delimChars:
            tokenizer.endToken()
        else:
            tokenizer.addToToken(char)

    def handleEnd(self, tokenizer):
        tokenizer.endToken()


class Tokenizer(object):
    """
    A class for tokenizing strings.

    It isn't particularly efficient.  Performance-wise, it is probably quite
    slow.  However, it is intended to be very customizable.  It provides many
    hooks to allow subclasses to override and extend its behavior.
    """
    STATE_NORMAL        = 0
    STATE_IN_QUOTE      = 1

    def __init__(self, state, value):
        self.value = value
        self.index = 0
        self.end = len(self.value)

        if isinstance(state, list):
            self.stateStack = state[:]
        else:
            self.stateStack = [state]

        self.currentToken = None
        self.tokens = []

        self.__processedEnd = False

    def getTokens(self, stop_at_end=True):
        tokens = []

        while True:
            token = self.getNextToken(stop_at_end)
            if token == None:
                break
            tokens.append(token)

        return tokens

    def getNextToken(self, stop_at_end=True):
        # If we don't currently have any tokens to process,
        # call self.processNextChar()
        while not self.tokens:
            if (not stop_at_end) and self.index >= self.end:
                # If stop_at_end is True, we let processNextChar()
                # handle the end of string as normal.  However, if stop_at_end
                # is False, the string value we have received so far is partial
                # (the caller might append more to it later), so return None
                # here without handling the end of the string.
                return None
            if self.__processedEnd:
                # If there are no more tokens and we've already reached
                # the end of the string, return None
                return None
            self.processNextChar()

        return self.__popToken()

    def __popToken(self):
        token = self.tokens[0]
        del self.tokens[0]
        return token

    def getPartialToken(self):
        return self.currentToken

    def processNextChar(self):
        if self.index >= self.end:
            if self.__processedEnd:
                raise IndexError()
            self.__processedEnd = True
            state = self.stateStack[-1]
            state.handleEnd(self)
            return

        char = self.value[self.index]
        self.index += 1

        state = self.stateStack[-1]
        state.handleChar(self, char)

    def pushState(self, state):
        self.stateStack.append(state)

    def popState(self):
        self.stateStack.pop()
        if not self.stateStack:
            raise Exception('cannot pop last state')

    def addToToken(self, char):
        if self.currentToken == None:
            self.currentToken = char
        else:
            self.currentToken += char

    def endToken(self):
        if self.currentToken == None:
            return

        self.tokens.append(self.currentToken)
        self.currentToken = None


class SimpleTokenizer(Tokenizer):
    def __init__(self, value):
        Tokenizer.__init__(self, [NormalState()], value)


def escape_arg(arg):
    """
    escape_arg(arg) --> escaped_arg

    This performs string escaping that can be used with SimpleTokenizer.
    (It isn't sufficient for passing strings to a shell.)
    """
    if arg.find('"') >= 0:
        if arg.find("'") >= 0:
            s = re.sub(r'\\', r'\\\\', arg)
            s = re.sub("'", "\\'", s)
            return "'%s'" % (s,)
        else:
            return "'%s'" % (arg,)
    elif arg.find("'") >= 0:
        return '"%s"' % (arg,)
    else:
        return arg


def escape_args(args):
    return ' '.join([escape_arg(a) for a in args])
