begin_version
4
end_version
begin_metric
1
end_metric
2
begin_variable
var0
-1
2
Atom visited(x0y0z0)
NegatedAtom visited(x0y0z0)
end_variable
begin_variable
var1
-1
2
Atom visited(x0y0z1)
NegatedAtom visited(x0y0z1)
end_variable
4
begin_numeric_variable
battery-level
-1
end_numeric_variable
begin_numeric_variable
x
-1
end_numeric_variable
begin_numeric_variable
y
-1
end_numeric_variable
begin_numeric_variable
z
-1
end_numeric_variable
0
begin_state
1
1
end_state
begin_numeric_state
9.0
0.0
0.0
0.0
end_numeric_state
begin_goal
2
0 0
1 0
end_goal
begin_numeric_goal
3
+ 1*1 == 0
+ 1*2 == 0
+ 1*3 == 0
end_numeric_goal
9
begin_operator
decrease_x 
0
0
2
+ 1*0 +  - 1.0 >= 0
+ 1*1 +  - 1.0 >= 0
2
0 := + 1*0 +  - 1.0
1 := + 1*1 +  - 1.0
1
end_operator
begin_operator
decrease_y 
0
0
2
+ 1*0 +  - 1.0 >= 0
+ 1*2 +  - 1.0 >= 0
2
0 := + 1*0 +  - 1.0
2 := + 1*2 +  - 1.0
1
end_operator
begin_operator
decrease_z 
0
0
2
+ 1*0 +  - 1.0 >= 0
+ 1*3 +  - 1.0 >= 0
2
0 := + 1*0 +  - 1.0
3 := + 1*3 +  - 1.0
1
end_operator
begin_operator
increase_x 
0
0
2
+ 1*0 +  - 1.0 >= 0
+ 1*1 <= 0
2
0 := + 1*0 +  - 1.0
1 := + 1*1 +  + 1.0
1
end_operator
begin_operator
increase_y 
0
0
2
+ 1*0 +  - 1.0 >= 0
+ 1*2 <= 0
2
0 := + 1*0 +  - 1.0
2 := + 1*2 +  + 1.0
1
end_operator
begin_operator
increase_z 
0
0
2
+ 1*0 +  - 1.0 >= 0
+ 1*3 +  - 1.0 <= 0
2
0 := + 1*0 +  - 1.0
3 := + 1*3 +  + 1.0
1
end_operator
begin_operator
recharge 
0
0
3
+ 1*1 == 0
+ 1*2 == 0
+ 1*3 == 0
1
0 :=  + 9.0
1
end_operator
begin_operator
visit x0y0z0
0
1
0 0 -1 0
4
+ 1*0 +  - 1.0 >= 0
- 1*1 == 0
- 1*2 == 0
- 1*3 == 0
1
0 := + 1*0 +  - 1.0
1
end_operator
begin_operator
visit x0y0z1
0
1
0 1 -1 0
4
+ 1*0 +  - 1.0 >= 0
- 1*1 == 0
- 1*2 == 0
- 1*3 +  + 1.0 == 0
1
0 := + 1*0 +  - 1.0
1
end_operator
0
