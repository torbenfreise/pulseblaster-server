# Copyright (c) 2026 SpinCore Technologies, Inc.
# http://www.spincore.com
#
# This software is provided 'as-is', without any express or implied warranty.
# In no event will the authors be held liable for any damages arising from the
# use of this software.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely, subject to the following restrictions:
#
# 1. The origin of this software must not be misrepresented; you must not
# claim that you wrote the original software. If you use this software in a
# product, an acknowledgement in the product documentation would be appreciated
# but is not required.
# 2. Altered source versions must be plainly marked as such, and must not be
# misrepresented as being the original software.
# 3. This notice may not be removed or altered from any source distribution.
#
# Version 20260108
# This file has been modified from the original SpinCore distribution.


"""PulseBlaster class to provide a higher level of abstraction for the PulseBlaster board.

The PulseBlaster class gives users more functionality with their boards,
allowing for programming of individual channels, visualization of pulse sequences,
and automatic firmware reading. Errors are also reported instantly,
without having to check the debug log
"""

from collections import deque

import matplotlib.pyplot as plt

from spincore import spinapi


class Instruction:
    """
    A class to represent PulseBlaster instructions

    ...

    Attributes
    ----------
    flags : int
        determines state of each TTL output bit.
    inst : int
        determines which type of instruction is to be executed
    inst_data : int
        data to be used with the previous 'inst' field
    length : int
        duration of the pulse program instruction, specified in ns

    Methods
    -------
    program():
        Programs the instruction onto the currently selected board
    """

    def __init__(self, flags, inst, inst_data, length):
        """
        Constructs alll the necessary attributes for the instruction object

        Parameters
        ----------
        flags : int
            determines state of each TTL output bit.
        inst : int
            determines which type of instruction is to be executed
        inst_data : int
            data to be used with the previous 'inst' field
        length : int
            duration of the pulse program instruction, specified in ns
        """

        self.flags = flags
        self.inst = inst
        self.inst_data = inst_data
        self.length = length

    def __str__(self):
        """
        Convert instruction into a string representation for readability

        Parameters
        ----------
        None

        Returns
        -------
        str
            formatted string that represents the contents of the instruction
        """

        opcodes = [
            "CONTINUE",
            "STOP",
            "LOOP",
            "END LOOP",
            "JSR",
            "RTS",
            "BRANCH",
            "LONG DELAY",
            "WAIT",
        ]

        return (
            f"{format(self.flags, '#026b')} | "
            f"{format(opcodes[self.inst], '^10s')} | "
            f"{self.inst_data} | {self.length} ns"
        )


def program(self):
    """
    Programs the instruction onto the currently selected board

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    rc = spinapi.pb_inst_pbonly(self.flags, self.inst, self.inst_data, self.length)
    if rc < 0:
        raise PulseBlasterError(f"pb_inst failed ({rc}): {spinapi.pb_get_error()}")
    return rc


class PulseBlasterError(Exception):
    """Base exception for PulseBlaster-related errors."""

    pass


class BoardNotFoundError(PulseBlasterError):
    """Raised when no PulseBlaster board is found."""

    pass


class InvalidChannelError(PulseBlasterError):
    """Raised when an invalid channel is accessed."""

    pass


class FirmwareMismatchError(PulseBlasterError):
    """Raised when the firmware is not recognized"""

    pass


class PulseBlaster:
    """
    A class to represent a PulseBlaster board

    ...

    Attributes
    ----------
    channels : int
        the number of TTL output channels on the board.
    clock : int
        the core clock frequency in MHz.
    memory : int
        the amount of programmable instruction memory.
    board_number : int
        the board number recognized by SpinAPI.
    queues : list[list[(int, float)]]
        the queues for each channels custom timing, awaiting compilation.
    instructions : list[Instruction]
        the list of instructions awaiting programming.
    running : bool
        flag that indicates if the board is currently running a program

    Methods
    -------
    start(self):
        Starts the PulseBlaster board.
    reset(self):
        Resets the PulseBlaster board.
    stop(self):
        Stops the PulseBlaster board.
    add_inst(self, flags, inst, inst_data, length):
        Adds instruction with specified parameters.
    program(self):
        Programs the PulseBlaster board with instructions awaiting in queue.
    set_channel(self, channel, values):
        Sets the specified channel to the pulse sequence given in values.
    visualize_channels(self, *args):
        Plots the expected logical output of specified channels (all if none specified).
    compile_channels(self):
        Compiles all channel's custom pulse sequence into instructions.
    _match_firmware(self):
        Matches the firmware of the board to specify given parameters
    """

    # Assume default board is 0, core clock frequency is 100 MHz
    def __init__(self, clock=0):
        """Initializes the PulseBlaster board and sets up parameters.

        Args:
            clock (int, optional): User-specified core clock frequency
                in MHz. Defaults to firmware reading.
        """

        self.running = (
            False  # Flag if board is running (Leave here so exit() function works properly)
        )

        print("Initializing new PulseBlaster board.")

        # Display SpinAPI version
        print(f"SpinAPI version: {spinapi.pb_get_version()}")

        # Have user select proper board
        board_number = 0  # Default
        board_count = spinapi.pb_count_boards()
        if board_count <= 0:
            raise BoardNotFoundError("No boards found on your system")

        if board_count > 1:
            while True:
                try:
                    board_number = int(input(f"Enter board number (0-{board_count - 1}): "))
                    if 0 <= board_number < board_count:
                        break
                except ValueError:
                    pass
                print("Invalid board number.")
        else:
            board_number = 0

        if spinapi.pb_select_board(board_number) != 0:
            raise PulseBlasterError(f"Failed to select board: {spinapi.pb_get_error()}")

        if spinapi.pb_init() != 0:
            raise PulseBlasterError(f"Failed to initialize: {spinapi.pb_get_error()}")

        # Set member variables
        self.channels, self.clock, self.memory = self._match_firmware()
        self.board_number = board_number
        self.queues = [[] for _ in range(self.channels)]
        self.instructions = []  # Instruction queue

        # Check if user has input their own clock frequency
        if clock != 0:
            self.clock = clock

        # Set core clock frequency
        spinapi.pb_core_clock(self.clock)

        # Print status
        print("Initiated new PulseBlaster board.")

    # Release PulseBlaster board
    def __del__(self):
        """Closes the PulseBlaster board upon object deletion."""
        spinapi.pb_close()
        print("Closed PulseBlaster board.")

    # Start the PulseBlaster board
    def start(self):
        """Starts the PulseBlaster board program execution."""
        if spinapi.pb_start() != 0:
            raise PulseBlasterError(
                f"Failed to start PulseBlaster program: {spinapi.pb_get_error()}"
            )
        print("PulseBlaster program has been started.")
        self.running = True

    # Reset the PulseBlaster board
    def reset(self):
        """Resets the PulseBlaster board to beginning of program."""
        if spinapi.pb_reset() != 0:
            raise PulseBlasterError(
                f"Failed to reset PulseBlaster program: {spinapi.pb_get_error()}"
            )
        print("PulseBlaster board has been reset.")
        self.running = True

    # Stop the PuleBlaster board
    def stop(self):
        """Stops the currently running PulseBlaster program."""
        if spinapi.pb_stop() != 0:
            raise PulseBlasterError(
                f"Failed to stop PulseBlaster program: {spinapi.pb_get_error()}"
            )
        print("PulseBlaster board has been stopped.")
        self.running = False

    # Add new instruction
    def add_inst(self, flags, inst, inst_data, length):
        """Adds an instruction to the PulseBlaster instruction queue.

        Args:
            flags (int): Bitmask of TTL output states.
            inst (int): Instruction type.
            inst_data (int): Data associated with the instruction.
            length (float): Duration of the instruction in nanoseconds.

        Returns:
            int: The index of the newly added instruction.
        """
        inst_pos = len(self.instructions)
        self.instructions.append(Instruction(flags, inst, inst_data, length))
        return inst_pos

    # Prints the status of the board
    def status(self):
        """Prints the current status of the PulseBlaster board"""
        s = spinapi.pb_read_status()
        print("Current state of PulseBlaster board:")
        if s & 1:
            print("Stopped")
        if s & 2:
            print("Reset")
        if s & 4:
            print("Running")
        if s & 8:
            print("Waiting")

    # Program the board with current instruction queue
    def program(self):
        """Programs the PulseBlaster board with the current list of instructions.

        This sends the instruction queue to the hardware and clears the queue.
        """
        # Validate number of instructions
        if len(self.instructions) > self.memory:
            print("Warning: Too many instructions")
            input("Please press a key to continue. ")
        # Error check pb_start_programming() call
        if spinapi.pb_start_programming(spinapi.PULSE_PROGRAM) != 0:
            raise PulseBlasterError(
                f"Failed to start programming PulseBlaster program: {spinapi.pb_get_error()}"
            )
        # Program each instruction
        for instr in self.instructions:
            instr.program()
        # Error check pb_stop_programming() call
        if spinapi.pb_stop_programming() != 0:
            raise PulseBlasterError(
                f"Failed to stop programming PulseBlaster program: {spinapi.pb_get_error()}"
            )
        # Clear instruction queue
        self.instructions.clear()

    # Set channel with specific pattern
    def set_channel(self, channel, values):
        """Defines a pulse squence for a specific output channel.

        Args:
            channel (int): The channel number to configure.
            values (list of tuple): A list of (value, duration) pairs,
                where 'value' is 0 or 1 (logical level), and 'duration' is in nanoseconds.
        """
        # Validate channel number
        if channel < 0 or channel >= self.channels:
            print("Error: Invalid channel specified")
            input("Please press a key to continue. ")
            self.exit()
        for val, duration in values:
            # Validate logical value
            if val not in (1, 0):
                print("Error: Channel values must be a 1 or a 0")
                input("Please press a key to continue. ")
                self.exit()
            # Validate duration (needs actual board-specific limits)
            if duration <= 0:
                print("Error: Invalid pulse duration")
                input("Please press a key to continue. ")
                self.exit()
            # Add to channel queue
            self.queues[channel].append((val, duration))

    # Plot patterns generated using 'set_channel()' function
    def visualize_channels(self, *args):
        """Visualizes the pulse patterns programmed into channels.

        Args:
            *args: Optional list of specific channel numbers to visualize.
                If none are given, all channels with defined pulses are visualized.
        """
        channels = []
        num_channels = 0

        # If channels are given as arguments, only plot those channels
        if args:
            # Validate channels
            for channel in args:
                if channel not in range(self.channels) or not self.queues[channel]:
                    print("Error: Invalid channel specified")
                    input("Please press a key to continue. ")
            channels = args
            num_channels = len(args)
        # If no channels are given as arguemnts, plot all channels that have been programmed
        else:
            # Determine which channels are being programmed
            channels = [i for i in range(self.channels) if self.queues[i]]
            num_channels = len(channels)

        # Initialize plot
        fig, axes = plt.subplots(num_channels, 1, figsize=(12, 2.5 * num_channels), sharex=True)

        # Make waveforms last for entire duration
        max_time = 0
        for channel in channels:
            current_time = 0
            for _, duration in self.queues[channel]:
                current_time += duration
            if current_time > max_time:
                max_time = current_time

        if num_channels == 1:
            axes = [axes]  # Ensure axes is always iterable

        for ax, channel_name in zip(axes, channels):
            time = []
            voltage = []
            current_time = 0

            for level, duration in self.queues[channel_name]:
                time.append(current_time)
                voltage.append(level)
                current_time += duration
                time.append(current_time)
                voltage.append(level)

            # Extend the last value to the global max_time
            if time and time[-1] < max_time:
                time.append(max_time)
                voltage.append(voltage[-1])

            # Plot the channel
            ax.plot(time, voltage, drawstyle="steps-post", color="red")
            ax.set_ylim(-0.2, 1.2)
            ax.set_yticks([0, 1])
            ax.set_yticklabels(["0", "1"])
            ax.set_ylabel(channel_name)

        # Plot everything
        axes[-1].set_xlabel("Time (ns)")
        plt.suptitle("SpinCore Technologies Inc.")
        axes[-1].set_xlim(-0.10, max_time)
        plt.tight_layout(rect=(0.03, 0, 1, 0.95))
        plt.show()

    # Compile channel patterns into instructions
    def compile_channels(self):
        """Compiles user-defined pulse sequences into hardware instructions.

        Returns:
            int: The index of the first instruction generated.
        """
        # Generate timelines for each channel
        timelines = [deque() for _ in range(self.channels)]
        for ch, queue in enumerate(self.queues):
            time_cursor = 0
            for value, duration in queue:
                time_cursor += duration
                timelines[ch].append((time_cursor, value))

        # Gather all unique event times
        all_times = sorted(set(t for q in timelines for (t, _) in q))

        instructions = []
        prev_time = 0
        current_state = 0x000000  # 24-bit bitmask for channels

        for t in all_times:
            duration = t - prev_time

            # Update state based on transitions at this time
            for ch in range(self.channels):
                while timelines[ch] and timelines[ch][0][0] == t:
                    _, val = timelines[ch].popleft()
                    if val == 1:
                        current_state |= 1 << ch
                    else:
                        current_state &= ~(1 << ch)

            instructions.append(Instruction(current_state, spinapi.CONTINUE, 0, duration))
            prev_time = t
        inst_beginning = len(self.instructions)
        self.instructions += instructions
        # Reset queues for this feature to be used again if necessary
        self.queues = [[] for _ in range(self.channels)]
        return inst_beginning

    def _match_firmware(self) -> tuple[int, float, int]:
        """Determines board specifications based on the firmware ID.

        Returns:
            tuple: A tuple of (channels, clock frequency, memory) depending on the board firmware.

        Notes:
            This function currently handles known firmware IDs via pattern matching.
            Unknown firmware raises an error.
        """
        # Get firmware id
        fw = spinapi.pb_get_firmware_id()

        # Calculate readable firmware ID
        fw_id = f"{fw // 256}-{fw % 256}"

        # Match firmware ID
        match fw_id:
            case "8-14":
                return (21, 200.0, 4096)
            case "9-7":
                return (21, 100.0, 4096)
            case "9-19":
                return (21, 300.0, 4096)
            case "12-10":
                return (4, 75.0, 4096)
            case "12-12":
                return (4, 75.0, 4096)
            case "12-15":
                return (4, 75.0, 4096)
            case "12-16":
                return (8, 75.0, 4096)
            case "13-12":
                return (24, 100.0, 4096)
            case "17-10":
                return (21, 400.0, 4096)
            case "17-11":
                return (21, 500.0, 4096)
            case "17-14":
                return (21, 500.0, 4096)
            case "17-16":
                return (21, 500.0, 4096)
            case "19-9":
                return (12, 100.0, 4096)
            case "19-15":
                return (12, 100.0, 4096)
            case "19-17":
                return (24, 100.0, 4096)
            case "22-2":
                return (24, 100.0, 4096)
            case "24-2":
                return (21, 300.0, 4096)
            case "24-3":
                return (21, 250.0, 4096)
            case "24-6":
                return (24, 200.0, 4096)
            case "24-9":
                return (24, 300.0, 4096)
            case "25-1":
                return (24, 100.0, 4096)
            case "26-1":
                return (24, 100.0, 4096)
            case "26-3":
                return (12, 100.0, 4096)
            case "26-4":
                return (12, 100.0, 4096)
            case "27-8":
                return (24, 500.0, 4096)
            case "27-10":
                return (24, 500.0, 4096)
            case "28-1":
                return (24, 100.0, 4096)
            case "29-1":
                return (24, 100.0, 4096)
            case "29-2":
                return (12, 100.0, 4096)
            case "29-3":
                return (24, 100.0, 8192)
            case "32-1":
                return (24, 100.0, 4096)
            case "33-1":
                return (24, 500.0, 4096)
            case "33-3":
                return (24, 500.0, 4096)
            case _:
                raise FirmwareMismatchError("Unkown Firmware")

    def exit(self):
        if self.running:
            self.stop()
