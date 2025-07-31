# cross_call_demo.py
import nested_demo as nd               # Alias-Import (ganze Datei)
from nested_demo import helper_1 as h1 # Alias-Import (Einzelfunktion)

def x0():
    print("x0  – Level 0")

    def x1():
        print("x1  – Level 1")

        def x2():
            print("x2  – Level 2")

            def x3():
                print("x3  – Level 3")
                # --------------------------------------------------
                # 1) Aufruf per Alias-Modul:    nd.outer()
                # 2) Aufruf per Alias-Funktion: h1(...)
                # --------------------------------------------------
                nd.outer()          # ruft die komplette Nested-Kette aus nested_demo.py
                h1(99)              # ruft helper_1() aus nested_demo.py

            # --- Level 3 aufrufen --------------------------------
            x3()

        # --- Level 2 aufrufen ------------------------------------
        x2()

    # --- Level 1 aufrufen ----------------------------------------
    x1()
