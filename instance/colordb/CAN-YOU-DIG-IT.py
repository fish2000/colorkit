                return dict(
                    version=3,
                    shape=(len(self),),
                    descr=[(name, '%s%s%s')] % (
                        ndtype.byteorder,
                        ndtype.kind,
                        ndtype.itemsize))
