import re
from collections import defaultdict

class GelişmişArama:
    def __init__(self, veri_listesi=None):
        self.liste = veri_listesi or []
        self.index_tablosu = defaultdict(list)
        if self.liste:
            self._index_oluştur()

    def _index_oluştur(self):
        for i, item in enumerate(self.liste):
            if hasattr(item, 'title'):
                self.index_tablosu[item.title[0].lower()].append((item.title, i))
            elif hasattr(item, 'name'):
                self.index_tablosu[item.name[0].lower()].append((item.name, i))

    def ara(self, hedef):
        if not hedef or not self.liste:
            return []

        hedef = hedef.strip().lower()
        sonuçlar = []
        
        ilk_harf = hedef[0] if hedef else ''
        
        for kelime, indeks in self.index_tablosu.get(ilk_harf, []):
            if hedef in kelime.lower() or re.search(hedef, kelime, re.IGNORECASE):
                sonuçlar.append((kelime, indeks))
        
        return sonuçlar