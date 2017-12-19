using System;
using System.Collections.Generic;
using System.Linq;
using System.Web;
using System.Web.UI;
using System.Web.UI.WebControls;

public partial class Form : System.Web.UI.Page
{
    internal class Attraction
    {
        public string name;
        public string address;
        public int price;
        public int rating;
        public Dictionary<string, bool> d;
        public string workHours;

        public Attraction(string name, string address, int price, int rating, Dictionary<string, bool> d, string workHours)
        {
            //constructor
            this.name = name;
            this.address = address;
            this.price = price;
            this.rating = rating;
            this.d = new Dictionary<string, bool>();
            this.d = d;
            this.workHours = workHours;
        }

    }
    public static Dictionary<string, bool> DicBuild()
    {
        Dictionary<string, bool> d = new Dictionary<string, bool>();
        d.Add("shopping", false);
        d.Add("sport", false);
        d.Add("history", false);
        d.Add("museums", false);
        d.Add("nature", false);
        d.Add("food", false);
        d.Add("party", false);
        return d;
    }
    internal static Attraction[] Create()
    {
        Dictionary<string, bool>[] darr = new Dictionary<string, bool>[10];
        for (int i = 0; i <= 9; i++)
        {
            darr[i] = DicBuild();
        }
        Attraction[] a = new Attraction[10];
        darr[0]["history"] = true;
        darr[1]["museums"] = true;
        darr[2]["nature"] = true;
        darr[3]["history"] = true;
        darr[4]["history"] = true;
        darr[5]["party"] = true;
        darr[6]["shopping"] = true;
        darr[7]["sport"] = true;
        darr[8]["food"] = true;
        darr[9]["shopping"] = true;
        a[0] = new Attraction("Big Ben", "westminster SW1A 0AA", 0, 5, darr[0], "any time!");
        a[1] = new Attraction("The British museum", "Great Russell St", 0, 5, darr[1], "10-17");
        a[2] = new Attraction("Hide Park", "London, UK", 0, 4, darr[2], "any time!");
        a[3] = new Attraction("Tower of London", "St Katharine's&Wapping", 20, 3, darr[3], "9-16");
        a[4] = new Attraction("Buckingham Palace", "westminster SW1A 1AA", 25, 5, darr[4], "9-19");
        a[5] = new Attraction("London Club", "SE 1 7PB", 32, 4, darr[5], "11-18");
        a[6] = new Attraction("Oxford Street", "Oxford St", 0, 4, darr[6], "8-21");
        a[7] = new Attraction("Emirates Stadium", "Hornsey Rd, London N7 7 AJ", 150, 2, darr[7], "saturday noon");
        a[8] = new Attraction("Street food union", "51-53 Rupert St", 10, 2, darr[8], "11-15");
        a[9] = new Attraction("Primark", "Oxford Street&3 Tottenham Court Road", 0, 3, darr[9], "9-22");
        return a;
    }
    internal class Tourist
    {
        public int budget;
        public int shopping;
        public int sport;
        public int history;
        public int museums;
        public int nature;
        public int food;
        public int party;
        public override string ToString()
        {
            string st = "budget= " + this.budget + "shopping:" + this.shopping + "sport:" + this.sport + "history:" + this.history +
                "museums:" + this.museums + "nature:" + this.nature + "food:" + this.food + "party:" + this.party;
            return st;
        }
        public static int Change(string s)
        {
            if (s == "Alot") return 6;
            if (s == "Yes") return 4;
            if (s == "Maybe") return 2;
            else return 0;

        }
        public Tourist(string budget, string shopping, string sport, string museums, string history, string nature
            , string food, string party)
        {
            this.budget = Change(budget);
            this.shopping = Change(shopping);
            this.sport = Change(sport);
            this.museums = Change(museums);
            this.history = Change(history);
            this.nature = Change(nature);
            this.food = Change(food);
            this.party = Change(party);
        }
    }
    internal static List<string> Must(Tourist t)
    {
        List<string> must = new List<string>();
        if (t.shopping == 6) must.Add("shopping");
        if (t.sport == 6) must.Add("sport");
        if (t.history == 6) must.Add("history");
        if (t.museums == 6) must.Add("museums");
        if (t.nature == 6) must.Add("nature");
        if (t.food == 6) must.Add("food");
        if (t.party == 6) must.Add("party");
        return must;
    }
    internal static List<string> Should(Tourist t)
    {
        List<string> should = new List<string>();
        if (t.shopping == 4 || t.shopping == 2) should.Add("shopping");
        if (t.sport == 4 || t.sport == 2) should.Add("sport");
        if (t.history == 4 || t.history == 2) should.Add("history");
        if (t.museums == 4 || t.museums == 2) should.Add("museums");
        if (t.nature == 4 || t.nature == 2) should.Add("nature");
        if (t.food == 4 || t.food == 2) should.Add("food");
        if (t.party == 4 || t.party == 2) should.Add("party");
        return should;
    }
    internal static List<string> Dont(Tourist t)
    {
        List<string> dont = new List<string>();
        if (t.shopping == 0) dont.Add("shopping");
        if (t.sport == 0) dont.Add("sport");
        if (t.history == 0) dont.Add("history");
        if (t.museums == 0) dont.Add("museums");
        if (t.nature == 0) dont.Add("nature");
        if (t.food == 0) dont.Add("food");
        if (t.party == 0) dont.Add("party");
        return dont;
    }
    internal static List<string>[] CreateLists(Tourist t)
    {
        List<string>[] lists = new List<string>[3];
        lists[0] = Must(t);
        lists[1] = Should(t);
        lists[2] = Dont(t);
        return lists;

    }
    internal static List<string> Match(Attraction[] attraction, List<string> must, List<string> should, List<string> dont)
    {
        bool test;
        List<string> arranged_att = new List<string>();
        foreach (string s in must)
        {
            foreach (Attraction a in attraction)
            {
                if (a.d.TryGetValue(s, out test))
                {
                    if (test == true && a.rating * 2 > 4)
                    {
                        arranged_att.Add(a.name);
                    }
                }
            }
        }
        foreach (string s in should)
        {
            foreach (Attraction a in attraction)
            {
                if (a.d.TryGetValue(s, out test))
                {
                    if (test == true && a.rating * 2 > 6)
                    {
                        arranged_att.Add(a.name);
                    }
                }
            }
        }
        foreach (string s in dont)
        {
            foreach (Attraction a in attraction)
            {
                if (a.d.TryGetValue(s, out test))
                {
                    if (test == true && a.rating * 2 > 8)
                    {
                        arranged_att.Add(a.name);
                    }
                }
            }
        }
        return arranged_att;
    }

    protected void Page_Load(object sender, EventArgs e)
    {

        Tourist t = new Tourist(Request.Form.Get("budget"), Request.Form.Get("shopping"), Request.Form.Get("sport"), Request.Form.Get("history"),
            Request.Form.Get("museums"), Request.Form.Get("nature"), Request.Form.Get("food"), Request.Form.Get("party"));
        List<string>[] lists = new List<string>[3];
        lists[0] = CreateLists(t)[0];
        lists[1] = CreateLists(t)[1];
        lists[2] = CreateLists(t)[2];
        Attraction[] a = new Attraction[10];
        a = Create();
        List<string> arr = new List<string>();
        arr = Match(a, lists[0], lists[1], lists[2]);
        foreach (string s in arr)
        {
            Response.Write(s+"<br>");
        }


    }
}