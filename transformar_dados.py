import json
from datetime import date

# Categorias para campanha por estilo de adversário
MATCHUP_CATEGORIES = [
    {"id": "pace",      "label": "Pace (times rápidos)",         "stat": "pace",      "source": "attack_style", "hi": True},
    {"id": "fg3a",      "label": "3PA (times que arremessam 3)", "stat": "fg3a",      "source": "base",         "hi": True},
    {"id": "drives",    "label": "Drives/jogo",                  "stat": "drives",    "source": "drives",       "hi": True},
    {"id": "postups",   "label": "Post-ups/jogo",                "stat": "postups",   "source": "postups",      "hi": True},
    {"id": "ortg",      "label": "Offensive Rating",             "stat": "ortg",      "source": "ratings",      "hi": True},
    {"id": "drtg",      "label": "Defensive Rating",             "stat": "drtg",      "source": "ratings",      "hi": False},
    {"id": "oreb",      "label": "ORB%",                         "stat": "oreb",      "source": "four_off",     "hi": True},
    {"id": "tov",       "label": "TOV% (times cuidadosos)",      "stat": "tov",       "source": "four_off",     "hi": False},
    {"id": "pts_fb",    "label": "Pts contra-ataque/jogo",       "stat": "pts_fb",    "source": "attack_style", "hi": True},
    {"id": "pts_paint", "label": "Pts no garrafão/jogo",         "stat": "pts_paint", "source": "attack_style", "hi": True},
]

def transformar(input_file, output_file, gamelog_file="dados_nba_gamelog.json"):
    raw = json.load(open(input_file))
    gamelog = json.load(open(gamelog_file))

    def idx(records, key="TEAM_ID"):
        return {r[key]: r for r in records}

    base    = idx(raw["base"])
    adv     = idx(raw["advanced"])
    misc    = idx(raw["misc"])
    opp     = idx(raw["opponent"])
    clutch  = idx(raw["clutch"])
    hustle  = idx(raw["hustle"])
    drives  = idx(raw["drives"])
    postups = idx(raw["postups"])
    sz_off  = {r["TEAM_ID"]: r for r in raw["shot_zones_off"]}
    sz_def  = {r["TEAM_ID"]: r for r in raw["shot_zones_def"]}
    abbr_map = {r["TEAM_ID"]: r["TEAM_ABBREVIATION"] for r in raw["drives"]}
    tid_map  = {v: k for k, v in abbr_map.items()}

    def rank_computed(d, higher=True):
        vals = sorted(d.items(), key=lambda x: x[1], reverse=higher)
        return {tid: i+1 for i,(tid,_) in enumerate(vals)}

    def rank_col(data, col, higher=True):
        vals = [(tid,d[col]) for tid,d in data.items() if col in d and d[col] is not None]
        vals.sort(key=lambda x: x[1], reverse=higher)
        return {tid: i+1 for i,(tid,_) in enumerate(vals)}

    all_tids = list(base.keys())

    ftr_c, opp_efg_c, opp_tov_c, opp_ftr_c = {}, {}, {}, {}
    for tid in all_tids:
        b=base.get(tid,{}); o=opp.get(tid,{})
        fga=b.get("FGA",0) or 0; fta=b.get("FTA",0) or 0
        ftr_c[tid] = round(fta/fga,3) if fga>0 else 0
        ofgm=o.get("OPP_FGM",0) or 0; ofg3m=o.get("OPP_FG3M",0) or 0
        ofga=o.get("OPP_FGA",0) or 0; ofta=o.get("OPP_FTA",0) or 0
        opp_efg_c[tid] = round((ofgm+0.5*ofg3m)/ofga,3) if ofga>0 else 0
        opp_tov_c[tid] = o.get("OPP_TOV",0) or 0
        opp_ftr_c[tid] = round(ofta/ofga,3) if ofga>0 else 0

    clutch_wpct = {tid:(clutch.get(tid,{}).get("W_PCT",0) or 0) for tid in all_tids}

    east = ["ATL","BOS","BKN","CHA","CHI","CLE","DET","IND","MIA","MIL","NYK","ORL","PHI","TOR","WAS"]
    e_teams = [(tid,base[tid].get("W",0)) for tid in all_tids if abbr_map.get(tid,"") in east]
    w_teams = [(tid,base[tid].get("W",0)) for tid in all_tids if abbr_map.get(tid,"") not in east]
    e_teams.sort(key=lambda x:x[1],reverse=True); w_teams.sort(key=lambda x:x[1],reverse=True)
    conf_rank = {}
    for i,(tid,_) in enumerate(e_teams): conf_rank[tid]=(i+1,"Leste")
    for i,(tid,_) in enumerate(w_teams): conf_rank[tid]=(i+1,"Oeste")

    def zone_freq_ranks(zone_raw, higher_is_better=True):
        zones = ["ra","nra","mid","c3","ab3"]
        ranks = {}
        for z in zones:
            freq_d, efg_d = {}, {}
            for tid in all_tids:
                zr = zone_raw.get(tid,{}).get(z,{})
                fga = zr.get("fga",0) or 0
                fgm = zr.get("fgm",0) or 0
                total_fga = sum(zone_raw.get(tid,{}).get(zz,{}).get("fga",0) or 0 for zz in zones)
                freq_d[tid] = fga/total_fga if total_fga>0 else 0
                is3 = z in ("c3","ab3")
                efg_d[tid] = (1.5*fgm/fga if is3 else fgm/fga) if fga>0 else 0
            ranks[f"{z}_freq"] = rank_computed(freq_d, higher_is_better)
            ranks[f"{z}_efg"]  = rank_computed(efg_d, higher_is_better)
        return ranks

    def get_zone_raw(sz, prefix=""):
        def safe(k): return sz.get(k,0) or 0
        p = prefix
        return {
            "ra":  {"fgm":safe(f"Restricted Area_{p}FGM"),  "fga":safe(f"Restricted Area_{p}FGA")},
            "nra": {"fgm":safe(f"In The Paint (Non-RA)_{p}FGM"), "fga":safe(f"In The Paint (Non-RA)_{p}FGA")},
            "mid": {"fgm":safe(f"Mid-Range_{p}FGM"),        "fga":safe(f"Mid-Range_{p}FGA")},
            "c3":  {"fgm":safe(f"Corner 3_{p}FGM"),         "fga":safe(f"Corner 3_{p}FGA")},
            "ab3": {"fgm":safe(f"Above the Break 3_{p}FGM"),"fga":safe(f"Above the Break 3_{p}FGA")},
        }

    zone_raw_off = {tid: get_zone_raw(sz_off.get(tid,{}), "") for tid in all_tids}
    zone_raw_def = {tid: get_zone_raw(sz_def.get(tid,{}), "OPP_") for tid in all_tids}
    zone_ranks_off = zone_freq_ranks(zone_raw_off, True)
    zone_ranks_def = zone_freq_ranks(zone_raw_def, False)

    ranks = {
        "ortg":          rank_col(adv,"OFF_RATING",True),
        "drtg":          rank_col(adv,"DEF_RATING",False),
        "netrtg":        rank_col(adv,"NET_RATING",True),
        "pace":          rank_col(adv,"PACE",True),
        "efg":           rank_col(adv,"EFG_PCT",True),
        "tov":           rank_col(adv,"TM_TOV_PCT",False),
        "oreb":          rank_col(adv,"OREB_PCT",True),
        "ftr":           rank_computed(ftr_c,True),
        "opp_efg":       rank_computed(opp_efg_c,False),
        "opp_tov":       rank_computed(opp_tov_c,True),
        "opp_ftr":       rank_computed(opp_ftr_c,False),
        "opp_oreb":      rank_col(opp,"OPP_OREB",False),
        "pts_fb":        rank_col(misc,"PTS_FB",True),
        "pts_paint":     rank_col(misc,"PTS_PAINT",True),
        "opp_pts_fb":    rank_col(misc,"OPP_PTS_FB",False),
        "opp_pts_paint": rank_col(misc,"OPP_PTS_PAINT",False),
        "drives":        rank_col(drives,"DRIVES",True),
        "postups":       rank_col(postups,"POST_TOUCHES",True),
        "deflections":   rank_col(hustle,"DEFLECTIONS",True),
        "charges":       rank_col(hustle,"CHARGES_DRAWN",True),
        "loose_balls":   rank_col(hustle,"LOOSE_BALLS_RECOVERED",True),
        "clutch_wpct":   rank_computed(clutch_wpct,True),
        "fg3a":          rank_col(base,"FG3A",True),
    }

    # Mapas de valor por time para campanha por estilo
    style_vals = {}
    for tid in all_tids:
        a=adv.get(tid,{}); b=base.get(tid,{}); m=misc.get(tid,{})
        dr=drives.get(tid,{}); pu=postups.get(tid,{})
        style_vals[tid] = {
            "pace":      a.get("PACE",0) or 0,
            "fg3a":      b.get("FG3A",0) or 0,
            "drives":    dr.get("DRIVES",0) or 0,
            "postups":   pu.get("POST_TOUCHES",0) or 0,
            "ortg":      a.get("OFF_RATING",0) or 0,
            "drtg":      a.get("DEF_RATING",0) or 999,
            "oreb":      (a.get("OREB_PCT",0) or 0)*100,
            "tov":       (a.get("TM_TOV_PCT",0) or 0)*100,
            "pts_fb":    m.get("PTS_FB",0) or 0,
            "pts_paint": m.get("PTS_PAINT",0) or 0,
        }

    def get_top7(stat_id, hi):
        vals = [(tid, style_vals[tid][stat_id]) for tid in all_tids if tid in style_vals]
        vals.sort(key=lambda x: x[1], reverse=hi)
        return {tid for tid,_ in vals[:7]}

    # Processar game log
    # Extrair adversário de cada jogo
    def get_opp_abbr(matchup):
        if " @ " in matchup:
            return matchup.split(" @ ")[1]
        elif " vs. " in matchup:
            return matchup.split(" vs. ")[0]
        return None

    # Agrupar jogos por time
    games_by_team = {}
    for g in gamelog:
        tid = g["TEAM_ID"]
        if tid not in games_by_team:
            games_by_team[tid] = []
        opp_abbr = get_opp_abbr(g.get("MATCHUP",""))
        games_by_team[tid].append({
            "wl": g.get("WL",""),
            "opp_abbr": opp_abbr,
        })

    def calc_matchup_records(tid):
        records = {}
        team_games = games_by_team.get(tid, [])
        for cat in MATCHUP_CATEGORIES:
            top7 = get_top7(cat["id"], cat["hi"])
            top7_abbrs = {abbr_map.get(t,"") for t in top7}
            # Remove o próprio time
            own_abbr = abbr_map.get(tid,"")
            top7_abbrs.discard(own_abbr)
            w=0; l=0
            for g in team_games:
                if g["opp_abbr"] in top7_abbrs:
                    if g["wl"] == "W": w+=1
                    elif g["wl"] == "L": l+=1
            records[cat["id"]] = {"label": cat["label"], "w": w, "l": l}
        return records

    pt_by_team = {}
    pt_names = {
        "Transition":"Transição","PRBallHandler":"Pick & Roll (arm.)",
        "PRRollMan":"Pick & Roll (pivô)","Isolation":"Isolação",
        "Spotup":"Spot Up","Postup":"Post Up","Handoff":"Handoff",
        "Cut":"Cortes","OffScreen":"Após corta-luz",
    }
    for pt_key,records in raw["play_types"].items():
        for r in records:
            tid=r["TEAM_ID"]
            if tid not in pt_by_team: pt_by_team[tid]={}
            pt_by_team[tid][pt_key]=r

    def build_zones(zone_raw, zone_ranks, tid):
        zones = ["ra","nra","mid","c3","ab3"]
        names = {"ra":"Área restrita","nra":"Garrafão (não-RA)","mid":"Meia distância","c3":"Zona Morta","ab3":"Above the break 3"}
        result = []
        total_fga = sum(zone_raw.get(tid,{}).get(z,{}).get("fga",0) or 0 for z in zones)
        for z in zones:
            zr = zone_raw.get(tid,{}).get(z,{})
            fga = zr.get("fga",0) or 0
            fgm = zr.get("fgm",0) or 0
            freq = round(fga/total_fga*100,1) if total_fga>0 else 0
            is3 = z in ("c3","ab3")
            efg = round((1.5*fgm/fga if is3 else fgm/fga)*100,1) if fga>0 else 0
            result.append({
                "name": names[z],
                "freq": freq,
                "freq_rank": zone_ranks.get(f"{z}_freq",{}).get(tid,0),
                "efg": efg,
                "efg_rank": zone_ranks.get(f"{z}_efg",{}).get(tid,0),
            })
        return result

    def pizza_drives(dr):
        total=dr.get("DRIVES",1) or 1
        fga=dr.get("DRIVE_FGA",0) or 0; pas=dr.get("DRIVE_PASSES",0) or 0
        tov=dr.get("DRIVE_TOV",0) or 0; pf=dr.get("DRIVE_PF",0) or 0
        other=max(0,total-fga-pas-tov-pf)
        return {"shots":round(fga/total*100,1),"passes":round(pas/total*100,1),
                "tov":round(tov/total*100,1),"fouls":round(pf/total*100,1),"other":round(other/total*100,1)}

    def pizza_postups(pt):
        total=pt.get("POST_TOUCHES",1) or 1
        fga=pt.get("POST_TOUCH_FGA",0) or 0; pas=pt.get("POST_TOUCH_PASSES",0) or 0
        tov=pt.get("POST_TOUCH_TOV",0) or 0; pf=pt.get("POST_TOUCH_FOULS",0) or 0
        other=max(0,total-fga-pas-tov-pf)
        return {"shots":round(fga/total*100,1),"passes":round(pas/total*100,1),
                "tov":round(tov/total*100,1),"fouls":round(pf/total*100,1),"other":round(other/total*100,1)}

    teams_out = {}
    for tid in all_tids:
        b=base.get(tid,{}); a=adv.get(tid,{}); m=misc.get(tid,{})
        o=opp.get(tid,{}); cl=clutch.get(tid,{}); hu=hustle.get(tid,{})
        dr=drives.get(tid,{}); pu=postups.get(tid,{}); pt=pt_by_team.get(tid,{})
        abbr=abbr_map.get(tid,str(tid)); name=b.get("TEAM_NAME","")
        w=b.get("W",0); l=b.get("L",0); cr=conf_rank.get(tid,(0,""))

        pt_list=[]
        for pt_key,pt_data in pt.items():
            pt_list.append({"name":pt_names.get(pt_key,pt_key),
                "freq":round((pt_data.get("POSS_PCT",0) or 0)*100,1),
                "ppp":round(pt_data.get("PPP",0) or 0,2),
                "freq_rank":0,"eff_rank":0})
        pt_list.sort(key=lambda x:x["freq"],reverse=True)
        for pt_key in pt_names:
            fv=[(t2,(pt_by_team.get(t2,{}).get(pt_key,{}).get("POSS_PCT",0) or 0)) for t2 in all_tids if pt_by_team.get(t2,{}).get(pt_key)]
            ev=[(t2,(pt_by_team.get(t2,{}).get(pt_key,{}).get("PPP",0) or 0)) for t2 in all_tids if pt_by_team.get(t2,{}).get(pt_key)]
            fv.sort(key=lambda x:x[1],reverse=True); ev.sort(key=lambda x:x[1],reverse=True)
            fr={t:i+1 for i,(t,_) in enumerate(fv)}; er={t:i+1 for i,(t,_) in enumerate(ev)}
            for p in pt_list:
                if p["name"]==pt_names.get(pt_key):
                    p["freq_rank"]=fr.get(tid,0); p["eff_rank"]=er.get(tid,0)

        teams_out[abbr]={
            "name":name,"abbreviation":abbr,"rec":f"{w}-{l}",
            "conf_rank":cr[0],"conf":cr[1],
            "clutch":{"w":cl.get("W",0),"l":cl.get("L",0),
                      "wpct":round((cl.get("W_PCT",0) or 0)*100,1),
                      "rank":ranks["clutch_wpct"].get(tid,0)},
            "ratings":{
                "ortg":{"value":round(a.get("OFF_RATING",0) or 0,1),"rank":ranks["ortg"].get(tid,0)},
                "drtg":{"value":round(a.get("DEF_RATING",0) or 0,1),"rank":ranks["drtg"].get(tid,0)},
                "netrtg":{"value":round(a.get("NET_RATING",0) or 0,1),"rank":ranks["netrtg"].get(tid,0)},
            },
            "four_factors_off":{
                "efg":{"value":round((a.get("EFG_PCT",0) or 0)*100,1),"rank":ranks["efg"].get(tid,0)},
                "tov":{"value":round((a.get("TM_TOV_PCT",0) or 0)*100,1),"rank":ranks["tov"].get(tid,0)},
                "oreb":{"value":round((a.get("OREB_PCT",0) or 0)*100,1),"rank":ranks["oreb"].get(tid,0)},
                "ftr":{"value":round(ftr_c.get(tid,0),2),"rank":ranks["ftr"].get(tid,0)},
            },
            "four_factors_def":{
                "opp_efg":{"value":round(opp_efg_c.get(tid,0)*100,1),"rank":ranks["opp_efg"].get(tid,0)},
                "opp_tov":{"value":round(opp_tov_c.get(tid,0),1),"rank":ranks["opp_tov"].get(tid,0)},
                "opp_oreb":{"value":round((o.get("OPP_OREB",0) or 0),1),"rank":ranks["opp_oreb"].get(tid,0)},
                "opp_ftr":{"value":round(opp_ftr_c.get(tid,0),2),"rank":ranks["opp_ftr"].get(tid,0)},
            },
            "attack_style":{
                "pace":{"value":round(a.get("PACE",0) or 0,1),"rank":ranks["pace"].get(tid,0)},
                "pts_fb":{"value":round(m.get("PTS_FB",0) or 0,1),"rank":ranks["pts_fb"].get(tid,0)},
                "pts_paint":{"value":round(m.get("PTS_PAINT",0) or 0,1),"rank":ranks["pts_paint"].get(tid,0)},
            },
            "defense_style":{
                "opp_pace":{"value":round(a.get("PACE",0) or 0,1),"rank":ranks["pace"].get(tid,0)},
                "opp_pts_fb":{"value":round(m.get("OPP_PTS_FB",0) or 0,1),"rank":ranks["opp_pts_fb"].get(tid,0)},
                "opp_pts_paint":{"value":round(m.get("OPP_PTS_PAINT",0) or 0,1),"rank":ranks["opp_pts_paint"].get(tid,0)},
            },
            "hustle":{
                "deflections":{"value":round(hu.get("DEFLECTIONS",0) or 0,1),"rank":ranks["deflections"].get(tid,0)},
                "charges":{"value":round(hu.get("CHARGES_DRAWN",0) or 0,2),"rank":ranks["charges"].get(tid,0)},
                "loose_balls":{"value":round(hu.get("LOOSE_BALLS_RECOVERED",0) or 0,1),"rank":ranks["loose_balls"].get(tid,0)},
            },
            "shot_zones_off": build_zones(zone_raw_off, zone_ranks_off, tid),
            "shot_zones_def": build_zones(zone_raw_def, zone_ranks_def, tid),
            "drives":{"per_game":round(dr.get("DRIVES",0) or 0,1),"rank":ranks["drives"].get(tid,0),"pizza":pizza_drives(dr)},
            "postups":{"per_game":round(pu.get("POST_TOUCHES",0) or 0,1),"rank":ranks["postups"].get(tid,0),"pizza":pizza_postups(pu)},
            "play_types":pt_list,
            "matchup_records": calc_matchup_records(tid),
        }

    output={
        "season": raw["season"],
        "period": raw["period"],
        "updated": raw["updated"],
        "teams": teams_out
    }
    with open(output_file,"w") as f:
        json.dump(output,f,indent=2)
    print(f"  {output_file} criado com {len(teams_out)} times.")

print("Transformando períodos...")
transformar("dados_nba_full.json", "times_full.json")
transformar("dados_nba_30d.json",  "times_30d.json")
transformar("dados_nba_14d.json",  "times_14d.json")
print("Feito!")