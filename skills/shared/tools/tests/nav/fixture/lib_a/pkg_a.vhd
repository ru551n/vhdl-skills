library ieee;
use ieee.std_logic_1164.all;

package pkg_a is
  type state_t is (idle, busy);
  function add1(x : natural) return natural;
end package;

package body pkg_a is
  function add1(x : natural) return natural is
  begin
    return x + 1;
  end function;
end package body;
