# nested_demo.py
def outer():
    print("outer – Level 0")

    def level1():
        helper_0()                     # externer Call (s. u.)
        print("level1 – Level 1")

        def level2(a: int):
            print(f"level2 – Level 2, a={a}")

            def level3(b: int):
                print(f"level3 – Level 3, b={b}")

                def level4(c: int):
                    print(f"level4 – Level 4, c={c}")
                    helper_1(c)        # noch ein Dummy-Call

                # --- Level 4 aufrufen --------------------------
                level4(b + 1)

            # --- Level 3 aufrufen ------------------------------
            level3(a + 1)

        # --- Level 2 aufrufen ----------------------------------
        level2(0)

    # --- Level 1 aufrufen --------------------------------------
    level1()


# ===== Zwei einfache Hilfsfunktionen (stehen „extern“) =========
def helper_0():
    print("helper_0 () – außerhalb der Nested-Kette")


def helper_1(x: int):
    print(f"helper_1 () – argument = {x}")
