                    old_dict = dict(filter(
                        lambda pair: (pair[0], new_dtype.type(pair[1])),
                        self._asdict().items()))


            
            '''
            @classmethod
            def _make(cls, iterable, new=None, len=len):
                if new is None:
                    new = cls.__base__.__new__
                result = new(cls, map(cls.dtype.type, iterable))
                print "New result: %s" % result
                numargs = len(__channels__)
                if len(result) != numargs:
                    raise TypeError('Expected %s arguments, got %d' % (
                        numargs, len(result)))
                return result
            '''
