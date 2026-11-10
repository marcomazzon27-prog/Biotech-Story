"""Importa nel canone i Cicli 1-5 scritti in chat. Uso: python canon/seed.py mnemosine.db"""
import sqlite3, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
STATS = ("power","money","rep","guilt","bonds","risk","health")

MAIN = {  # stat finali dopo Ciclo 5
 "elia":   ("Dr. Elia Riva", "Biologo molecolare, ex quant", "Cernobbio", (4,6,3,7,9,9,3)),
 "arthur": ("Sir Arthur Blackwood", "Investment banker, chairman emeritus", "Londra", (10,8,2,10,3,9,2)),
 "sofia":  ("Sofia Venturi", "Venture capitalist, Helix Ventures", "Milano", (4,6,3,7,7,8,5)),
}
SEC = {  # id: (nome, ruolo, luogo, ciclo di morte)
 "beatrice":("Beatrice Corsi","Avvocato/notaio","Como",None), "tommaso":("Tommaso Ferri","Giornalista investigativo","Milano",None),
 "yuki":("Dr. Yuki Tanaka","Scienziata","Singapore",None), "krane":("Victor Krane","Private equity","New York",None),
 "nadia":("Nadia El Mansour","Avvocata data protection","Bruxelles",None), "croft":("Lord Alistair Croft","Rivale storico di Arthur","Londra",3),
 "elena":("Elena Riva","Oncologa, sorella di Elia","Milano",None), "sasha":("Sasha Petrov","Fixer","Zurigo",None),
 "aisha":("Aisha Rahman","Fondo sovrano Meridian","Abu Dhabi",None), "clara":("Clara Neri","Chef","Bellagio",None),
 "lorenzo":("Lorenzo Bardi","Hacker/analista","Milano",None), "greppi":("Paolo Greppi","CEO Aurelia Pharma","Basilea",None),
 "marco":("Dr. Marco Fanti","Lab manager Riva Biosciences","Como",3), "rachel":("Rachel Stein","IP lawyer","New York",None),
 "klaus":("Dr. Klaus Weber","Direttore laboratorio","Basilea",None), "hale":("Margaret Hale","Ricercatrice trial 1994","Inghilterra",2),
}
ORGS = {"riva":"Riva Biosciences","bw":"Blackwood & Sterling","helix":"Helix Ventures","aurelia":"Aurelia Pharma",
        "meridian":"Meridian Sovereign Fund","registro":"Il Registro","stein":"Stein & Associates","crispino":"Clinica San Crispino"}

# strength 0 = relazione chiusa dalla morte di una delle parti
REL = [("elia","elena","family","Sorella",9),("elia","sofia","romance","Attrazione/alleanza",7),("elia","clara","romance","Attrazione",5),
 ("elia","arthur","conflict","Preda/predatore",8),("elia","krane","conflict","Scalata ostile",7),("elia","yuki","conflict","Rivalita scientifica",6),
 ("elia","marco","business","Lab manager",0),("elia","beatrice","business","Consulente legale",5),("elia","aisha","business","Offerta Registro",4),
 ("arthur","sofia","secret","Ricatto occulto",8),("arthur","krane","business","Soci",7),("arthur","croft","conflict","Nemici da 50 anni",0),
 ("arthur","tommaso","secret","Fonte riservata",6),("arthur","nadia","secret","Corruzione",7),("arthur","greppi","business","Finanziamenti storici",8),
 ("sofia","krane","conflict","Ricatto/contro-ricatto",8),("sofia","aisha","business","Term sheet",5),("sofia","nadia","conflict","Esposizione stampa",5),
 ("sofia","tommaso","business","Fonte giornalistica",4),("krane","greppi","business","Scalata Aurelia",8),("krane","aisha","conflict","Competizione fondi",6),
 ("aisha","rachel","business","IP due diligence",7),("aisha","nadia","business","Compliance",4),("tommaso","nadia","knowledge","Fonti incrociate",5),
 ("tommaso","beatrice","knowledge","Notizie dal lago",3),("nadia","sasha","conflict","Caccia al breach",6),("sasha","krane","business","Riciclaggio",5),
 ("clara","elena","knowledge","Amiche",4),("lorenzo","nadia","business","Analisi breach",5),("lorenzo","greppi","conflict","Ex dipendente",4),
 ("greppi","marco","secret","Ricatto",0),("beatrice","arthur","secret","Vecchi affari",3),("elia","klaus","business","Validazione IVDR",4),
 ("arthur","hale","secret","Trial 1994",0)]

# (id, ciclo, attore, tipo, nome, causa, luogo, descrizione)
EV = [
 ("e01",1,"elia","scienza","Scoperta del biomarker",None,"Cernobbio","Campione anomalo: proteina legata alla memoria."),
 ("e02",1,"arthur","salute","Diagnosi riservata",None,"Londra","Deterioramento cognitivo precoce."),
 ("e03",1,"sofia","finanza","Pitch di Riva Biosciences","e01","Milano","Sofia riceve il pitch e propone un term sheet."),
 ("e04",2,"elia","regolatorio","Ispezione AIFA/NAS","e01","Cernobbio","Qualcuno ha parlato del biomarker."),
 ("e05",2,"elia","tradimento","Marco Fanti copia i dati","e01","Cernobbio","Marco ricattato da Aurelia (debiti di gioco)."),
 ("e06",2,"arthur","morte","Morte di Margaret Hale","e02","Inghilterra","Suicidio apparente; qualcuno chiude i buchi del 1994."),
 ("e07",2,"arthur","alleanza","Arthur offre esclusiva a Tommaso","e06","Londra","Documenti in cambio di tempo; Tommaso registra."),
 ("e08",2,"sofia","finanza","Krane offre 120M per Riva","e03","Zurigo","Offerta ostile con liquidation preference 2x."),
 ("e09",2,"sofia","breach","Data breach San Crispino",None,"Milano","40.000 cartelle esposte; tra esse quella di Arthur."),
 ("e10",3,"elia","morte","Morte di Marco Fanti","e05","Como","Investito sul lungolago; cassetta a Zurigo con copia del Registro."),
 ("e11",3,"arthur","morte","Morte di Lord Croft",None,"Londra","Causa non chiarita (promessa aperta)."),
 ("e12",3,"sofia","finanza","Aisha acquista il 3% di Riva","e08","Zurigo","Meridian entra nel capitale."),
 ("e13",3,"sofia","carriera","Helix scarica Sofia","e12","Milano","Declassata dal consiglio."),
 ("e14",3,"elia","scienza","Yuki pubblica il preprint contrario","e01","Singapore","Il titolo di Riva crolla."),
 ("e15",4,"elia","normativa","Regolamento UE 2026/47","e14","Bruxelles","Doppia validazione indipendente in 90 giorni."),
 ("e16",4,"arthur","finanza","Aurelia fallisce la fase III",None,"Basilea","Titolo -40%; Krane compra al ribasso."),
 ("e17",4,"sofia","stampa","Tommaso pubblica l'inchiesta sul Registro","e09","Milano","Nome di Sofia a pag. 3."),
 ("e18",4,"sofia","finanza","Convocazione Baur au Lac","e17","Zurigo","Aisha offre 500M per il Registro."),
 ("e19",4,"elia","fuga","Clara porta Elia in luogo sicuro","e15","Como","Su richiesta di Elena."),
 ("e20",5,"elia","scienza","Validazione fallita con cutoff singolo","e15","Basilea","NPV 83,6%: serve doppio cutoff."),
 ("e21",5,"arthur","legale","La SEC apre un fascicolo","e16","New York","Opzioni call OTM prima dell'annuncio."),
 ("e22",5,"sofia","finanza","Royalty monetization 80M per 25%","e13","Milano","Non diluitivo; cap 3x."),
 ("e23",5,"elia","legale","Due diligence IP di Aisha","e18","Zurigo","Chain of title opaca (dati USA)."),
 ("e24",5,"elia","scienza","Rapporto p-tau217/Abeta42 porta NPV all'89%","e20","Como","Via d'uscita scientifica."),
]
# decisioni di canone: risolvono le incongruenze emerse in chat (es. date della madre di Elia)
FACTS = [
 ("f01","elia","ha_scaricato","dati di 2.400 pazienti da uno studio USA chiuso (Boston 2019)",1,0),
 ("f02","arthur","ha_coperto","il trial mortale del 1994",1,0),
 ("f03","registro","esiste_dal","2011, 40.000 cartelle",1,0),
 ("f04","sofia","favorisce","un fondo occulto collegato ad Arthur",1,0),
 ("f05","marco","ha_copiato","i dati di Mnemosine per Aurelia",1,2),
 ("f06","marco","custodiva","copia del Registro in una cassetta a Zurigo",1,3),
 ("f07","nadia","registra","le conversazioni con Arthur",1,5),
 ("f08","arthur","ha_comprato","opzioni Aurelia prima dell'annuncio",1,4),
 ("f09","elia","madre_diagnosi","2018 (Alzheimer precoce)",1,0),
 ("f10","elia","madre_morta","2021",1,0),
]
KNOW = [("arthur","f02","sa",0,None),("arthur","f03","sa",0,None),("arthur","f04","sa",0,None),("elia","f01","sa",0,None),
 ("sofia","f04","sa",0,None),("sofia","f02","sospetta",2,None),("tommaso","f02","sospetta",2,"arthur"),("elia","f05","sa",3,"marco"),
 ("elia","f06","sa",3,"marco"),("elia","f03","sa",3,"marco"),("nadia","f08","sa",5,None),("nadia","f07","sa",5,None),
 ("aisha","f01","sospetta",5,"rachel"),("rachel","f01","sa",5,None)]
SECRETS = [("f01","elia","brevetto nullo e carcere"),("f02","arthur","rovina e processo"),("f04","sofia","fine carriera"),("f08","arthur","reato SEC")]
PROMISES = [("p01","Chi ha ucciso Marco Fanti?",3),("p02","Come e morto Lord Croft?",3),("p03","Chi ha comprato opzioni Aurelia con i dati di Nadia?",4),
 ("p04","Cosa contiene la cassetta di Marco a Zurigo?",3),("p05","Elia cedera il Registro ad Aisha per sistemare la chain of title?",5),
 ("p06","Nadia usera le registrazioni su Arthur?",5),("p07","Chi e il mandante dietro la chiusura dei buchi del 1994?",2)]

def build(path):
    if os.path.exists(path): os.remove(path)
    c = sqlite3.connect(path)
    c.executescript(open(os.path.join(HERE,"schema.sql"), encoding="utf-8").read())
    c.executescript(open(os.path.join(HERE,"schema_v3.sql"), encoding="utf-8").read())
    for i,(n,r,p,st) in MAIN.items():
        c.execute("INSERT INTO entities(id,kind,name,role,tier,place) VALUES(?,?,?,?,?,?)",(i,"persona",n,r,"main",p))
        for s,v in zip(STATS,st): c.execute("INSERT INTO stats VALUES(?,?,?)",(i,s,v))
    for i,(n,r,p,d) in SEC.items():
        c.execute("INSERT INTO entities(id,kind,name,role,tier,place,status,died_cycle) VALUES(?,?,?,?,?,?,?,?)",
                  (i,"persona",n,r,"sec",p,"morto" if d else "vivo",d))
    for i,n in ORGS.items(): c.execute("INSERT INTO entities(id,kind,name) VALUES(?,?,?)",(i,"org",n))
    for a,b,t,l,s in REL: c.execute("INSERT INTO relations(a,b,type,label,strength) VALUES(?,?,?,?,?)",(a,b,t,l,s))
    for k,cy,ac,ty,nm,ca,lo,de in EV:
        c.execute("INSERT INTO events(id,cycle,kind,name,actor,location,description,origin) VALUES(?,?,?,?,?,?,?,?)",(k,cy,ty,nm,ac,lo,de,"storico"))
    for k,cy,ac,ty,nm,ca,lo,de in EV:
        c.execute("UPDATE events SET cause_event_id=? WHERE id=?",(ca,k))
    c.executemany("INSERT INTO facts VALUES(?,?,?,?,?,?)",FACTS)
    c.executemany("INSERT INTO knowledge VALUES(?,?,?,?,?)",KNOW)
    c.executemany("INSERT INTO secrets VALUES(?,?,?)",SECRETS)
    c.executemany("INSERT INTO promises(id,description,opened_cycle) VALUES(?,?,?)",PROMISES)
    for cy in range(1,6): c.execute("INSERT INTO cycles VALUES(?,?)",(cy,"storico"))
    c.commit(); return c

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv)>1 else "mnemosine.db"
    build(out).close(); print("Canone creato:", out)
