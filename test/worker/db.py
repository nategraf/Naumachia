import trol

class Db(trol.Database):
    challenges = trol.Set(typ=trol.Model)

    class Challenge(trol.Model):
        def __init__(self, name):
            self.id = name

        certificates = trol.Set(typ=trol.Model)
        strategies = trol.Set(typ=str)
        ready = trol.Property(typ=bool, alwaysfetch=True)

    class Certificate(trol.Model):
        def __init__(self, cn, text=None):
            self.id = cn
            if text:
                self.text = text
        
        text = trol.Property()
