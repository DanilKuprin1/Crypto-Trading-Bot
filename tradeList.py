class IsolatedPairsList:

    def __init__(self) -> None:
        self.arr = []
        pass
    
    def append(self, symbol:str):
        for symb in self.arr:
            if symb == symbol:
                self.arr.remove(symb)
                self.append(symbol)
                return True
        if len(self.arr) >= 10:
            self.arr.pop(0)
        self.arr.append(symbol)
        return True
    
    def removeMostUnused(self):
        if len(self.arr) > 0:
            return self.arr.pop(0)
        else:
            return None 
    
    def removeFromList(self,symbol):
        try:
            self.arr.remove(symbol)
        except:
            return -1
        else:
            return 1


            